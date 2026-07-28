export type RetrievedSnippet = {
  id: string
  title: string
  content: string
  score: number
}

export type AskResponse = {
  question: string
  retrieved_snippets: RetrievedSnippet[]
  draft: string
  grounded: boolean
}

type AskApiResponse = AskResponse

const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8020'

export async function askQuestion(question: string): Promise<AskApiResponse> {
  const response = await fetch(`${API_BASE_URL}/api/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: unknown; error?: string; message?: string }
      const detail = payload.detail
      if (typeof detail === 'string') {
        message = detail
      } else if (detail && typeof detail === 'object') {
        const nested = detail as { error?: string; message?: string }
        message = nested.message ?? nested.error ?? message
      } else {
        message = payload.message ?? payload.error ?? message
      }
    } catch {
      // Keep the HTTP-status message when the response body is not JSON.
    }
    throw new Error(message)
  }

  return (await response.json()) as AskApiResponse
}
