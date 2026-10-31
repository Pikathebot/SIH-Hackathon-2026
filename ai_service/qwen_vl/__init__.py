"""
Qwen-VL engine (general vision-language model served via llama.cpp llama-server, OpenAI-compatible API).

Import `ai_service.qwen_vl.wrapper` for real inference or
`ai_service.qwen_vl.mock` for the contract-conformant stand-in; the backend
engine registry (backend/app/engines.py) chooses between them.
"""
