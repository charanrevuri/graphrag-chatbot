import React, { useEffect, useRef } from "react";

function Bubble({ msg }) {
  if (msg.role === "user") {
    return <div className="bubble bubble-user">{msg.text}</div>;
  }
  if (msg.role === "status") {
    return <div className="bubble bubble-status">{msg.text}</div>;
  }
  if (msg.role === "rewrite") {
    return (
      <div className="bubble bubble-rewrite">
        <span>Interpreted as</span>
        {msg.text}
      </div>
    );
  }
  if (msg.role === "error") {
    return <div className="bubble bubble-error">⚠️ {msg.text}</div>;
  }
  if (msg.role === "system") {
    return <div className="bubble bubble-system">{msg.text}</div>;
  }
  // assistant
  return (
    <div className="bubble bubble-assistant">
      <div>{msg.text}</div>
      {msg.cypher && (
        <details className="cypher-details">
          <summary>View generated Cypher</summary>
          <pre>{msg.cypher}</pre>
        </details>
      )}
    </div>
  );
}

export default function ChatWindow({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-window">
      {messages.map((msg, i) => (
        <Bubble key={i} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
