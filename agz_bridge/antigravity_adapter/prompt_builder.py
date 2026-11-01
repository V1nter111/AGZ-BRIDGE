"""Converts OpenAI-compatible chat messages into structured prompts for Antigravity CLI."""
import json
from typing import Any, Dict, List, Optional


class PromptBuilder:
    BRIDGE_SYSTEM_PROMPT = (
        "You are an AI brain operating via AGZ Bridge. You are executing remotely for Agent Zero.\n"
        "ENVIRONMENT CONSTRAINT (CRITICAL):\n"
        "- All terminal execution, file system operations, web browsing, python execution, and computer use MUST run on the WORKER PC, NEVER on this host machine.\n"
        "- Do NOT execute local CLI tools on the host.\n"
        "- If you need actions taken, communicate through structured tool calls or the JSON format requested by the user/Agent Zero.\n"
    )

    @classmethod
    def format_tools_instruction(cls, tools: List[Dict[str, Any]]) -> str:
        """Format OpenAI tools into clear instructions for Gemini."""
        if not tools:
            return ""

        tool_defs = []
        for t in tools:
            if t.get("type") == "function" and "function" in t:
                fn = t["function"]
                tool_defs.append({
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                })

        instruction = (
            "\nAVAILABLE TOOLS ON WORKER PC:\n"
            + json.dumps(tool_defs, indent=2)
            + "\n\nTOOL USE INSTRUCTIONS:\n"
            + "- To use a tool on the Worker PC, output your tool call as a JSON object: "
            + '{"tool_name": "<name>", "tool_args": {<arguments>}}\n'
            + "- Or in standard tool call format if requested.\n"
            + "- Output only the JSON call when requesting a tool.\n"
        )
        return instruction

    @classmethod
    def build_initial_prompt(
        cls,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Build full synthesized prompt for turn 1 (or standalone turn).
        Combines system prompt, bridge isolation directive, tool schemas, and chat history.
        """
        sections: List[str] = [cls.BRIDGE_SYSTEM_PROMPT]

        if tools:
            sections.append(cls.format_tools_instruction(tools))

        # Separate system messages and user/assistant messages
        user_history: List[str] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Multimodal or block content
                text_parts = [
                    item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if role == "system":
                sections.append(f"System Directive:\n{content}")
            elif role == "user":
                user_history.append(f"User: {content}")
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    call_summary = json.dumps(tool_calls)
                    user_history.append(f"Assistant [Tool Call]: {call_summary}")
                else:
                    user_history.append(f"Assistant: {content}")
            elif role == "tool":
                call_id = msg.get("tool_call_id", "")
                name = msg.get("name", "")
                user_history.append(f"Tool Result [{name} | id:{call_id}]:\n{content}")

        if user_history:
            sections.append("\nConversation History & Current Request:\n" + "\n\n".join(user_history))

        return "\n\n".join(sections)

    @classmethod
    def build_turn_prompt(cls, new_message: Dict[str, Any]) -> str:
        """
        Build prompt for an incremental turn in an existing conversation.
        """
        role = new_message.get("role", "user")
        content = new_message.get("content", "")
        if isinstance(content, list):
            text_parts = [
                item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
            ]
            content = "\n".join(text_parts)

        if role == "tool":
            call_id = new_message.get("tool_call_id", "")
            name = new_message.get("name", "")
            return f"Tool Execution Result on Worker PC [{name} | id:{call_id}]:\n{content}"
        elif role == "user":
            return content
        elif role == "assistant":
            return f"Previous assistant output: {content}"
        else:
            return f"[{role.upper()}]: {content}"
