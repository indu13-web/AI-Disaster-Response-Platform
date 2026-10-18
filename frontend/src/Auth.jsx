import { useState } from "react";
import "./Auth.css";

const API = "http://127.0.0.1:8000";

export default function Auth({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const response = await fetch(`${API}/${mode === "signup" ? "signup" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          mode === "signup"
            ? { name, username, password }
            : { username, password }
        ),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Something went wrong");
      }

      setMessage(data.message);

      if (mode === "login") {
        onLogin(data.user);
      } else {
        setMode("login");
        setMessage("Account created! Please log in.");
      }
    } catch (error) {
      setMessage(error.message || "Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Disaster Response</h1>
        <p>Emergency Response Intelligence Platform</p>

        <div className="auth-tabs">
          <button type="button" onClick={() => { setMode("login"); setMessage(""); }}>
            Login
          </button>
          <button type="button" onClick={() => { setMode("signup"); setMessage(""); }}>
            Sign Up
          </button>
        </div>

        {mode === "signup" && (
          <label>
            Full name
            <input value={name} onChange={e => setName(e.target.value)} required />
          </label>
        )}

        <label>
          Username
          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            minLength={3}
            required
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>

        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? "Please wait..." : mode === "signup" ? "Create Account" : "Login"}
        </button>

        {message && <p className="auth-message">{message}</p>}
      </form>
    </div>
  );
}