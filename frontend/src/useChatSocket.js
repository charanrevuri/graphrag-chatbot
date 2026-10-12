import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws/chat/";

/**
 * Manages a single WebSocket connection to the Django Channels backend
 * and exposes the running chat history + connection status.
 */
export default function useChatSocket() {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("connecting"); // connecting | open | closed
  const [pending, setPending] = useState(false);
  const socketRef = useRef(null);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onopen = () => setStatus("open");
    socket.onclose = () => setStatus("closed");
    socket.onerror = () => setStatus("closed");

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "system") {
        setMessages((prev) => [...prev, { role: "system", text: data.message }]);
      } else if (data.type === "status") {
        setMessages((prev) => [
          ...prev,
          { role: "status", text: data.message, cypher: data.cypher },
        ]);
      } else if (data.type === "rewrite") {
        setMessages((prev) => [
          ...prev,
          { role: "rewrite", text: data.rewritten_question },
        ]);
      } else if (data.type === "answer") {
        setPending(false);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: data.answer,
            cypher: data.cypher,
            results: data.results,
            rewrittenQuestion: data.rewritten_question,
          },
        ]);
      } else if (data.type === "error") {
        setPending(false);
        setMessages((prev) => [
          ...prev,
          { role: "error", text: data.message, cypher: data.cypher },
        ]);
      }
    };

    return () => socket.close();
  }, []);

  const sendMessage = useCallback((text) => {
    if (!text.trim() || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text }]);
    setPending(true);
    socketRef.current.send(JSON.stringify({ message: text }));
  }, []);

  return { messages, status, pending, sendMessage };
}
