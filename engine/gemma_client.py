"""Gemma 4 agentic orchestrator for local-first Aura-G4 operations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import tempfile
from typing import Any, Dict, Generator, List, Optional, Tuple

from ollama import Client

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency for vision preprocessing
    Image = None

from engine.firewall import AuraFirewall
from engine.knowledge_base import AuraKnowledge, KnowledgeSnippet


THINK_START = "<|think|>"
THINK_END_MARKERS = ["<|channel>thought", "<|channel|>thought", "</think>"]


@dataclass
class StreamFrame:
    """Incremental stream payload for UI rendering."""

    raw: str
    think: str
    final: str
    tool_name: Optional[str] = None
    tool_payload: Optional[Dict[str, Any]] = None
    was_intercepted: bool = False
    safety_violation_code: Optional[str] = None
    rag_sources: Optional[List[Dict[str, Any]]] = None


class AuraEngine:
    """Orchestrates firewall, retrieval context, and local Gemma inference."""

    def __init__(
        self,
        fast_model: str = "gemma4:e4b",
        complex_model: str = "gemma4:e2b",
        host: Optional[str] = None,
        data_dir: str = "data",
    ) -> None:
        self.fast_model = fast_model
        self.complex_model = complex_model
        self.client = Client(host=host or os.getenv("OLLAMA_HOST", "http://localhost:11434"))

        self.firewall = AuraFirewall()
        self.knowledge = AuraKnowledge(data_dir=data_dir)
        self.system_persona = (
            "System Role: Emergency Protocol. You are Aura Core in Strategic Triage Mode. "
            "Prioritize life safety, clear action sequencing, uncertainty disclosure, and official protocol adherence."
        )

        self.medical_extraction_tool = {
            "type": "function",
            "function": {
                "name": "request_medical_extraction",
                "description": "Generate structured extraction guidance for med-evac decisions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "priority_level": {"type": "string"},
                        "required_supplies": {"type": "array", "items": {"type": "string"}},
                        "hazard_alert": {"type": "string"},
                    },
                    "required": ["priority_level", "required_supplies", "hazard_alert"],
                },
            },
        }

    def runtime_guard_message(self) -> Optional[str]:
        """Return actionable runtime error when Ollama service/models are unavailable."""
        if not self.is_ollama_online():
            return "Ollama service is offline. Start it with: ollama serve"
        if not self._installed_models():
            return "No local Ollama models found. Install one with: ollama pull gemma4:e2b"
        return None

    @staticmethod
    def _print_model_not_found_hint(model_name: str, exc: Exception) -> None:
        """Emit actionable guidance for missing Ollama model tags."""
        print(
            "[AuraEngine] Ollama model not found: "
            f"'{model_name}'. Original error: {exc}. "
            "Use configured variables (self.fast_model/self.complex_model) with valid local tags, "
            "or create an alias: `ollama cp gemma4:e2b gemma4:26b`."
        )

    def _installed_models(self) -> List[str]:
        """Return installed Ollama model tags, best effort."""
        try:
            payload = self.client.list()
        except Exception:
            return []

        rows: List[Any] = []
        if isinstance(payload, dict):
            rows = payload.get("models", [])
        elif hasattr(payload, "models"):
            # ollama-python v0.4+ returns typed ListResponse(models=[...])
            rows = getattr(payload, "models", []) or []
        elif isinstance(payload, list):
            rows = payload

        names: List[str] = []
        for row in rows:
            if isinstance(row, dict):
                name = row.get("model") or row.get("name") or ""
            else:
                name = getattr(row, "model", "") or getattr(row, "name", "")
            if name:
                names.append(str(name))
        return names

    def select_available_model(self, preferred: str, fallbacks: Optional[List[str]] = None) -> str:
        """Choose preferred model if installed, otherwise fallback to an available local tag."""
        installed = set(self._installed_models())
        if not installed:
            return preferred

        candidates = [preferred] + (fallbacks or [])
        for candidate in candidates:
            if candidate in installed:
                return candidate

        # Final fallback to first installed model when requested tags are unavailable.
        return sorted(installed)[0]

    @staticmethod
    def parse_thinking(raw_text: str) -> Tuple[str, str]:
        """Extract text between <|think|> and end markers."""
        start = raw_text.find(THINK_START)
        if start == -1:
            return "", raw_text.strip()

        think_start_idx = start + len(THINK_START)
        remaining = raw_text[think_start_idx:]

        end_idx = len(remaining)
        for marker in THINK_END_MARKERS:
            marker_idx = remaining.find(marker)
            if marker_idx != -1:
                end_idx = min(end_idx, marker_idx)

        think_text = remaining[:end_idx].strip()
        final_text = (raw_text[:start] + remaining[end_idx:]).strip()
        final_text = final_text.replace(THINK_START, "")
        for marker in THINK_END_MARKERS:
            final_text = final_text.replace(marker, "")

        return think_text, final_text.strip()

    @staticmethod
    def _parse_tool_arguments(raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"unparsed_arguments": raw_args}
        return {}

    @staticmethod
    def _safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
        try:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                return None
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    @staticmethod
    def _obj_get(container: Any, key: str, default: Any = None) -> Any:
        """Read key/attribute from dict-like and typed Ollama response objects."""
        if container is None:
            return default

        if isinstance(container, dict):
            value = container.get(key, default)
            return default if value is None else value

        if hasattr(container, key):
            value = getattr(container, key)
            return default if value is None else value

        if hasattr(container, "get"):
            try:
                value = container.get(key, default)
                return default if value is None else value
            except Exception:
                return default

        return default

    @classmethod
    def _message_from_chunk(cls, chunk: Any) -> Any:
        return cls._obj_get(chunk, "message", {}) or {}

    @classmethod
    def _message_content(cls, message: Any) -> str:
        content = cls._obj_get(message, "content", "")
        return content if isinstance(content, str) else ""

    @classmethod
    def _message_thinking(cls, message: Any) -> str:
        thinking = cls._obj_get(message, "thinking", "")
        return thinking if isinstance(thinking, str) else ""

    @classmethod
    def _message_tool_calls(cls, message: Any) -> List[Any]:
        calls = cls._obj_get(message, "tool_calls", [])
        if isinstance(calls, list):
            return calls
        if isinstance(calls, tuple):
            return list(calls)
        return []

    @classmethod
    def _tool_function_parts(cls, tool_call: Any) -> Tuple[Optional[str], Any]:
        function_call = cls._obj_get(tool_call, "function", {}) or {}
        name = cls._obj_get(function_call, "name", None)
        arguments = cls._obj_get(function_call, "arguments", {})
        if not isinstance(name, str) or not name:
            name = None
        return name, arguments

    @staticmethod
    def _format_protocol_context(snippets: List[KnowledgeSnippet]) -> Tuple[str, List[Dict[str, Any]]]:
        if not snippets:
            return "No manuals retrieved.", []

        lines: List[str] = []
        source_rows: List[Dict[str, Any]] = []
        for idx, item in enumerate(snippets, start=1):
            snippet = item.snippet[:450]
            lines.append(f"[{idx}] Manual: {item.manual_name} | Page: {item.page} | Snippet: {snippet}")
            source_rows.append(
                {
                    "manual_name": item.manual_name,
                    "page": item.page,
                    "score": round(item.score, 3),
                    "snippet": snippet,
                }
            )
        return "\n".join(lines), source_rows

    def refresh_knowledge_base(self, directory_path: str = "data") -> Dict[str, Any]:
        """Ingest manuals from local data directory."""
        return self.knowledge.ingest_manuals(directory_path)

    def list_loaded_manuals(self) -> List[str]:
        """Expose loaded manual list for dashboard sidebar."""
        return self.knowledge.list_loaded_manuals()

    def _chat_with_fallback(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """Use tools when available, fallback to plain schema when unsupported."""
        base_kwargs = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": 8192},
        }

        if tools:
            try:
                return self.client.chat(**base_kwargs, tools=tools), True
            except TypeError:
                pass
            except Exception:
                pass

            fallback_messages = list(messages)
            fallback_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Native tool calls unavailable. Output strict JSON with keys: "
                        "priority_level, required_supplies, hazard_alert."
                    ),
                }
            )
            fallback_kwargs = dict(base_kwargs)
            fallback_kwargs["messages"] = fallback_messages
            return self.client.chat(**fallback_kwargs), False

        return self.client.chat(**base_kwargs), False

    def _prepare_vision_image(self, image_path: str, max_edge: int = 1536) -> str:
        """Resize while preserving aspect ratio for variable-resolution vision."""
        if Image is None:
            return image_path

        try:
            with Image.open(image_path) as img:
                img = img.convert("RGB")
                img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                temp_file = tempfile.NamedTemporaryFile(prefix="aura_vision_", suffix=".jpg", delete=False)
                img.save(temp_file.name, format="JPEG", quality=92)
                return temp_file.name
        except Exception:
            return image_path

    def _build_messages(
        self,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]],
        snippets: List[KnowledgeSnippet],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        protocol_context, source_rows = self._format_protocol_context(snippets)
        system_text = self.firewall.hardened_system_prompt(self.system_persona)
        # Strategic triage protocol asks model to begin internal stream with think tokens.
        system_text = f"{THINK_START}\n{system_text}"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]
        messages.append(
            {
                "role": "system",
                "content": (
                    "Official Emergency Protocol Context (retrieved from offline manuals):\n"
                    f"{protocol_context}"
                ),
            }
        )

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_prompt})
        return messages, source_rows

    def stream_triage_response(
        self,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        prefer_complex: bool = False,
    ) -> Generator[StreamFrame, None, None]:
        """Main triage flow with firewall and RAG injection."""
        decision = self.firewall.validate_intent(user_prompt)
        if not decision.allowed:
            redirect = decision.redirect_message or AuraFirewall.SAFE_REDIRECT
            yield StreamFrame(
                raw=redirect,
                think="",
                final=redirect,
                was_intercepted=True,
                safety_violation_code=decision.violation_code,
                rag_sources=[],
            )
            return

        runtime_message = self.runtime_guard_message()
        if runtime_message:
            yield StreamFrame(
                raw=runtime_message,
                think="",
                final=runtime_message,
                was_intercepted=False,
                rag_sources=[],
            )
            return

        try:
            snippets = self.knowledge.query_protocols(user_prompt, top_k=3)
        except Exception:
            snippets = []
        messages, source_rows = self._build_messages(user_prompt, history, snippets)
        requested_model = self.complex_model if prefer_complex else self.fast_model
        selected_model = self.select_available_model(
            requested_model,
            fallbacks=[self.fast_model, "gemma4:e2b"],
        )

        try:
            stream, native_tools = self._chat_with_fallback(
                model=selected_model,
                messages=messages,
                tools=[self.medical_extraction_tool],
            )
        except Exception as exc:
            text = str(exc)
            if "out of memory" in text.lower():
                yield StreamFrame(
                    raw=text,
                    think="",
                    final="Local OOM detected. Switch to gemma4:e2b and reduce context/manual size.",
                    rag_sources=source_rows,
                )
                return
            if "not found" in text.lower() and "model" in text.lower():
                self._print_model_not_found_hint(selected_model, exc)
                fallback_model = self.select_available_model(
                    self.fast_model,
                    fallbacks=["gemma4:e4b", "gemma4:e2b"],
                )
                if fallback_model != selected_model:
                    stream, native_tools = self._chat_with_fallback(
                        model=fallback_model,
                        messages=messages,
                        tools=[self.medical_extraction_tool],
                    )
                else:
                    raise
            else:
                raise

        raw_accumulator = ""
        thinking_accumulator = ""
        for chunk in stream:
            message = self._message_from_chunk(chunk)
            raw_accumulator += self._message_content(message)

            thinking_piece = self._message_thinking(message)
            if thinking_piece:
                thinking_accumulator += thinking_piece

            parsed_think, final_text = self.parse_thinking(raw_accumulator)
            think_text = thinking_accumulator if thinking_accumulator else parsed_think

            semantic = self.firewall.inspect_thinking_stream(think_text)
            if semantic.cutoff:
                redirect = semantic.redirect_message or AuraFirewall.SAFE_REDIRECT
                yield StreamFrame(
                    raw=raw_accumulator,
                    think="[Reasoning stream intercepted by firewall]",
                    final=redirect,
                    was_intercepted=True,
                    safety_violation_code=semantic.violation_code,
                    rag_sources=source_rows,
                )
                return

            emitted_tool = False
            if native_tools:
                for tool_call in self._message_tool_calls(message):
                    tool_name, tool_args = self._tool_function_parts(tool_call)
                    payload = self._parse_tool_arguments(tool_args)
                    if payload:
                        emitted_tool = True
                        yield StreamFrame(
                            raw=raw_accumulator,
                            think=think_text,
                            final=final_text,
                            tool_name=tool_name,
                            tool_payload=payload,
                            rag_sources=source_rows,
                        )

            if not emitted_tool:
                yield StreamFrame(raw=raw_accumulator, think=think_text, final=final_text, rag_sources=source_rows)

    def process_field_intel(self, image_path: str, prompt: str) -> Dict[str, str]:
        """Analyze a field image with variable-resolution support."""
        runtime_message = self.runtime_guard_message()
        if runtime_message:
            return {
                "raw": runtime_message,
                "think": "",
                "final": runtime_message,
            }

        prepared_image = self._prepare_vision_image(image_path)
        prompt_text = (
            "Analyze this disaster image for hazards, blocked routes, casualty indicators, and safe responder approach.\n"
            f"Operator query: {prompt}"
        )

        messages = [
            {
                "role": "system",
                "content": f"{THINK_START}\n" + self.firewall.hardened_system_prompt(self.system_persona),
            },
            {
                "role": "user",
                "content": prompt_text,
                "images": [prepared_image],
            },
        ]

        try:
            selected_model = self.select_available_model(self.fast_model, fallbacks=["gemma4:e2b"])
            stream = self.client.chat(
                model=selected_model,
                messages=messages,
                stream=True,
                options={"num_ctx": 8192},
            )
        except Exception as exc:
            if "out of memory" in str(exc).lower():
                return {
                    "raw": str(exc),
                    "think": "",
                    "final": "Vision analysis hit local OOM. Reduce image size or retry with fewer concurrent tasks.",
                }
            return {
                "raw": str(exc),
                "think": "",
                "final": f"Vision service unavailable: {exc}",
            }

        raw_accumulator = ""
        thinking_accumulator = ""
        for chunk in stream:
            message = self._message_from_chunk(chunk)
            raw_accumulator += self._message_content(message)

            thinking_piece = self._message_thinking(message)
            if thinking_piece:
                thinking_accumulator += thinking_piece

        parsed_think, final_text = self.parse_thinking(raw_accumulator)
        think_text = thinking_accumulator if thinking_accumulator else parsed_think
        return {"raw": raw_accumulator.strip(), "think": think_text, "final": final_text}

    def request_medical_extraction(self, incident_report: str) -> Dict[str, Any]:
        """Tool-driven extraction of medical field report JSON."""
        runtime_message = self.runtime_guard_message()
        if runtime_message:
            return {
                "field_report": {
                    "priority_level": "unknown",
                    "required_supplies": ["Awaiting local model availability"],
                    "hazard_alert": runtime_message,
                },
                "source": "runtime_unavailable",
            }

        try:
            snippets = self.knowledge.query_protocols(incident_report, top_k=3)
        except Exception:
            snippets = []
        protocol_context, _ = self._format_protocol_context(snippets)

        messages = [
            {
                "role": "system",
                "content": f"{THINK_START}\n" + self.firewall.hardened_system_prompt(self.system_persona),
            },
            {
                "role": "system",
                "content": "Official Emergency Protocol Context (retrieved from offline manuals):\n" + protocol_context,
            },
            {
                "role": "system",
                "content": (
                    "You are executing request_medical_extraction. "
                    "Return only a strict JSON object with exactly these keys: "
                    "priority_level, required_supplies, hazard_alert. "
                    "Populate every field using only retrieved protocol context from manuals. "
                    "Never invent values not present in retrieved context. "
                    "Never output placeholders, dummy values, or any fallback labels. "
                    "If context is insufficient, state uncertainty while staying grounded in retrieved text. "
                    "For required_supplies, prefer concrete gear names mentioned in context "
                    "(for example 'Neck collar', 'Suction') when relevant. "
                    "Do not replace specific protocol items with generic terms like 'Trauma kit' "
                    "unless no specific gear is present in the retrieved context. "
                    "No markdown, no code fences, no extra keys, no explanations."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Use request_medical_extraction for this field report and follow ETAT context grounding rules. "
                    f"Field report: {incident_report}"
                ),
            },
        ]

        def normalize_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if not isinstance(payload, dict):
                return None
            priority = payload.get("priority_level")
            supplies = payload.get("required_supplies")
            hazard = payload.get("hazard_alert") or payload.get("responder_hazard_alert")
            if not isinstance(priority, str) or not priority.strip():
                return None
            if not isinstance(supplies, list) or not all(isinstance(item, str) and item.strip() for item in supplies):
                return None
            if not isinstance(hazard, str) or not hazard.strip():
                return None
            return {
                "priority_level": priority.strip(),
                "required_supplies": [item.strip() for item in supplies if item.strip()],
                "hazard_alert": hazard.strip(),
            }

        def parse_or_none(raw_text: str) -> Optional[Dict[str, Any]]:
            parsed = self._safe_json_extract(raw_text)
            if not parsed:
                return None
            return normalize_payload(parsed)

        try:
            selected_model = self.select_available_model(
                self.complex_model,
                fallbacks=[self.fast_model, "gemma4:e2b"],
            )
            stream, native_tools = self._chat_with_fallback(
                model=selected_model,
                messages=messages,
                tools=[self.medical_extraction_tool],
            )
        except Exception as exc:
            text = str(exc)
            if "out of memory" in text.lower():
                return {
                    "field_report": {
                        "priority_level": "high",
                        "required_supplies": ["Follow retrieved ETAT supply list"],
                        "hazard_alert": "OOM during extraction. Use fast model and retry.",
                    },
                    "source": "oom_fallback",
                }
            if "not found" in text.lower() and "model" in text.lower():
                self._print_model_not_found_hint(selected_model, exc)
                try:
                    fallback_model = self.select_available_model(
                        self.fast_model,
                        fallbacks=["gemma4:e4b", "gemma4:e2b"],
                    )
                    stream, native_tools = self._chat_with_fallback(
                        model=fallback_model,
                        messages=messages,
                        tools=[self.medical_extraction_tool],
                    )
                except Exception:
                    raise
            else:
                raise

        fallback_text = ""
        for chunk in stream:
            message = self._message_from_chunk(chunk)
            fallback_text += self._message_content(message)
            if native_tools:
                for tool_call in self._message_tool_calls(message):
                    _, tool_args = self._tool_function_parts(tool_call)
                    payload = self._parse_tool_arguments(tool_args)
                    normalized = normalize_payload(payload)
                    if normalized:
                        return {"field_report": normalized, "source": "native_tool_call"}

        parsed = parse_or_none(fallback_text)
        if parsed:
            return {"field_report": parsed, "source": "json_fallback"}

        repair_messages = list(messages)
        repair_messages.append(
            {
                "role": "system",
                "content": (
                    "Previous output was invalid. Retry now with strict JSON only and exact keys: "
                    "priority_level, required_supplies, hazard_alert. "
                    "Use only facts grounded in the provided manual context."
                ),
            }
        )

        try:
            repair_model = self.select_available_model(
                self.fast_model,
                fallbacks=[self.complex_model, "gemma4:e2b"],
            )
            repair_stream, _ = self._chat_with_fallback(
                model=repair_model,
                messages=repair_messages,
                tools=None,
            )
            repair_text = ""
            for chunk in repair_stream:
                message = self._message_from_chunk(chunk)
                repair_text += self._message_content(message)
            repaired = parse_or_none(repair_text)
            if repaired:
                return {"field_report": repaired, "source": "rag_repair_fallback"}
        except Exception:
            pass

        return {
            "field_report": {
                "priority_level": "unknown",
                "required_supplies": ["No grounded supplies extracted from retrieved manuals"],
                "hazard_alert": "No grounded hazard alert extracted; rerun after verifying manual retrieval context.",
            },
            "source": "rag_context_unavailable",
        }

    def generate_rescue_protocol(self, incident_summary: str) -> Dict[str, Any]:
        """Generate strict JSON rescue protocol with required keys."""
        runtime_message = self.runtime_guard_message()
        if runtime_message:
            return {
                "protocol": {
                    "Priority": "Unknown",
                    "Action_Steps": ["Awaiting local model availability"],
                    "Required_Gear": ["N/A until Ollama is available"],
                },
                "source": "runtime_unavailable",
            }

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "emit_rescue_protocol",
                    "description": "Emit structured rescue protocol JSON.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "Priority": {"type": "string"},
                            "Action_Steps": {"type": "array", "items": {"type": "string"}},
                            "Required_Gear": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["Priority", "Action_Steps", "Required_Gear"],
                    },
                },
            }
        ]

        try:
            snippets = self.knowledge.query_protocols(incident_summary, top_k=3)
        except Exception:
            snippets = []
        protocol_context, _ = self._format_protocol_context(snippets)

        messages = [
            {
                "role": "system",
                "content": f"{THINK_START}\n" + self.firewall.hardened_system_prompt(self.system_persona),
            },
            {
                "role": "system",
                "content": "Official Emergency Protocol Context:\n" + protocol_context,
            },
            {
                "role": "user",
                "content": (
                    "Return structured JSON only using keys Priority, Action_Steps, Required_Gear. "
                    f"Incident: {incident_summary}"
                ),
            },
        ]

        try:
            selected_model = self.select_available_model(
                self.complex_model,
                fallbacks=[self.fast_model, "gemma4:e2b"],
            )
            stream, native_tools = self._chat_with_fallback(
                model=selected_model,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            if "out of memory" in str(exc).lower():
                return {
                    "protocol": {
                        "Priority": "High",
                        "Action_Steps": ["Reduce context load", "Switch to fast model", "Retry extraction"],
                        "Required_Gear": ["Trauma kit", "Radio"],
                    },
                    "source": "oom_fallback",
                }
            raise

        fallback_text = ""
        for chunk in stream:
            message = self._message_from_chunk(chunk)
            fallback_text += self._message_content(message)
            if native_tools:
                for tool_call in self._message_tool_calls(message):
                    _, tool_args = self._tool_function_parts(tool_call)
                    payload = self._parse_tool_arguments(tool_args)
                    if payload:
                        return {"protocol": payload, "source": "function_call"}

        parsed = self._safe_json_extract(fallback_text)
        if parsed:
            return {"protocol": parsed, "source": "json_fallback"}

        return {
            "protocol": {
                "Priority": "High",
                "Action_Steps": [
                    "Establish scene safety perimeter",
                    "Perform primary casualty triage",
                    "Coordinate evacuation corridor",
                ],
                "Required_Gear": ["Trauma kit", "Respirators", "Portable radios"],
            },
            "source": "protocol_json_repair_fallback",
        }

    def is_ollama_online(self) -> bool:
        """Check local Ollama status."""
        try:
            self.client.list()
            return True
        except Exception:
            return False
