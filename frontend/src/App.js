import React, { useState } from "react";
import ChatWindow from "./components/ChatWindow";
import useChatSocket from "./useChatSocket";
import "./App.css";

export default function App() {
  const { messages, status, pending, sendMessage } = useChatSocket();
  const [input, setInput] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
    setInput("");
  };

  const suggestions = [
    "Which movies did Tom Hanks act in?",
    "Who directed The Matrix?",
    "List all movies in the Sci-Fi genre",
    "Who acted in Top Gun?",
  ];

  return (
    <div className="app">
      <header className="app-header">
        <h1>GraphRAG Movie Chatbot</h1>
        <span className={`status-dot status-${status}`} title={status} />
      </header>

      <ChatWindow messages={messages} />

      {messages.length <= 1 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} onClick={() => sendMessage(s)} className="suggestion-chip">
              {s}
            </button>
          ))}
        </div>
      )}

      <form className="input-row" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask something about the movie graph..."
          disabled={status !== "open"}
        />
        <button type="submit" disabled={status !== "open" || pending}>
          {pending ? "Thinking..." : "Send"}
        </button>
      </form>
    </div>
  );
}
