const BACKEND_URL = `${import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000"}/execute-tool`;

export async function executeTool(toolName, args) {
  try {
    const response = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name: toolName, arguments: args }),
      signal: AbortSignal.timeout(6000),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Backend tool execution failed");
    }

    const data = await response.json();

    if (data.success === false) {
      throw new Error(data.error || "Backend tool execution failed");
    }

    return data.data ?? {};
  } catch (error) {
    console.error("API Error:", error);
    return {
      error: error.name === "TimeoutError"
        ? "The service took too long to respond"
        : error.message,
    };
  }
}