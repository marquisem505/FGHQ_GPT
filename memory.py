from openai import OpenAI
from db import get_recent_messages, get_summary, save_summary

def should_summarize(recent_pairs:int)->bool:
    return recent_pairs >= 6  # after ~6 exchanges, condense

def build_context(user_id:int, client:OpenAI, system_prompt:str):
    # Pull long-term memory + recent messages
    long_mem = get_summary(user_id)
    recent = get_recent_messages(user_id, limit=12)

    msgs = [{"role":"system","content":system_prompt}]
    if long_mem:
        msgs.append({"role":"system","content":f"Long-term memory about user: {long_mem}"} )
    msgs.extend({"role":r,"content":c} for r,c in recent)
    return msgs

def maybe_update_summary(user_id:int, client:OpenAI):
    # Summarize last ~20 messages into durable memory
    history = get_recent_messages(user_id, limit=20)
    if not history: return
    user_turns = [c for r,c in history if r=="user"]
    assistant_turns = [c for r,c in history if r=="assistant"]

    prompt = [
        {"role":"system","content":"You compress conversation into stable, helpful memory."},
        {"role":"user","content":(
            "From the chat excerpts below, write a concise, evergreen memory of the user: "
            "goals, preferences, constraints, recurring tasks. Omit ephemeral details.\n\n"
            f"USER_MSGS:\n{user_turns}\nASSISTANT_MSGS:\n{assistant_turns}\n"
            "Output 3-6 bullet points, no more than 80 words total."
        )}
    ]
    resp = client.responses.create(model="gpt-5", input=prompt)
    summary = resp.output_text.strip()
    if summary:
        save_summary(user_id, summary)