import { useState } from 'react'
import './styles.css'
import { askQuestion, type AskResponse } from './api/client'

function App() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [approvalMessage, setApprovalMessage] = useState('')

  const hasResult = result !== null

  async function handleAsk() {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || loading) {
      return
    }

    setLoading(true)
    setError(null)
    setApprovalMessage('')

    try {
      const response = await askQuestion(trimmedQuestion)
      setResult(response)
    } catch (cause) {
      setResult(null)
      setError(
        cause instanceof Error
          ? cause.message
          : 'Unable to get a reply from the server.',
      )
    } finally {
      setLoading(false)
    }
  }

  function handleDiscard() {
    setQuestion('')
    setResult(null)
    setError(null)
    setApprovalMessage('')
    setLoading(false)
  }

  function handleApprove() {
    setApprovalMessage('Approved (not sent — no delivery destination in this task)')
  }

  return (
    <main className="app-shell">
      <section className="question-card">
        <h1>SFCollab Research Reply Agent</h1>
        <label className="question-label" htmlFor="question">
          Question
        </label>
        <div className="question-row">
          <input
            id="question"
            type="text"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a support question"
            aria-label="Question input"
          />
          <button type="button" onClick={handleAsk} disabled={loading || !question.trim()}>
            {loading ? 'Asking…' : 'Ask'}
          </button>
        </div>
        {error ? (
          <p className="status-message status-error" role="alert">
            {error}
          </p>
        ) : null}
        {approvalMessage ? <p className="status-message">{approvalMessage}</p> : null}
      </section>

      <section className="results-grid" aria-live="polite">
        <article className="panel evidence-panel" data-testid="evidence-panel">
          <h2>Retrieved Evidence</h2>
          {hasResult ? (
            result.retrieved_snippets.length > 0 ? (
              <div className="snippet-list">
                {result.retrieved_snippets.map((snippet) => (
                  <div key={snippet.id} className="snippet">
                    <h3>{snippet.title}</h3>
                    <p>{snippet.content}</p>
                    <p className="score">Score: {snippet.score.toFixed(3)}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-state">No relevant help content found for this question.</p>
            )
          ) : (
            <p className="empty-state">No question answered yet.</p>
          )}
        </article>

        <article
          className={`panel draft-panel ${hasResult && !result.grounded ? 'ungrounded' : ''}`}
          data-testid="draft-panel"
        >
          <h2>Draft Reply</h2>
          {hasResult ? (
            <>
              {!result.grounded ? <div className="refusal-badge">Ungrounded / refusal</div> : null}
              <p className="draft-text">{result.draft}</p>
              <div className="action-row">
                <button type="button" onClick={handleApprove}>
                  Approve
                </button>
                <button type="button" className="secondary" onClick={handleDiscard}>
                  Discard
                </button>
              </div>
            </>
          ) : (
            <p className="empty-state">No draft yet.</p>
          )}
        </article>
      </section>
    </main>
  )
}

export default App
