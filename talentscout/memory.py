from langchain.memory import ConversationBufferMemory

def make_memory() -> ConversationBufferMemory:
    # Store only minimal text to avoid PII sprawl; final data goes to consented store.
    return ConversationBufferMemory(
        memory_key="chat_history",
        input_key="input",
        output_key="output",
        return_messages=True
    )
