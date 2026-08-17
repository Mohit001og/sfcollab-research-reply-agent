import { useEffect, useRef, useState } from 'react'
import './styles.css'
import { askQuestion, submitFeedback, type AskResponse, type FeedbackRating } from './api/client'

function App() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [approvalMessage, setApprovalMessage] = useState('')
  const [feedbackSelection, setFeedbackSelection] = useState<FeedbackRating | null>(null)
  const [feedbackLocked, setFeedbackLocked] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const feedbackErrorTimer = useRef<number | null>(null)

  const hasResult = result !== null

  useEffect(() => {
    return () => {
      if (feedbackErrorTimer.current !== null) {
        window.clearTimeout(feedbackErrorTimer.current)
      }
    }
  }, [])

  function resetFeedbackState() {
    if (feedbackErrorTimer.current !== null) {
      window.clearTimeout(feedbackErrorTimer.current)
      feedbackErrorTimer.current = null
    }
    setFeedbackSelection(null)
    setFeedbackLocked(false)
    setFeedbackError(null)
  }

  function showFeedbackError(message: string) {
    if (feedbackErrorTimer.current !== null) {
      window.clearTimeout(feedbackErrorTimer.current)
    }
    setFeedbackError(message)
    feedbackErrorTimer.current = window.setTimeout(() => {
      setFeedbackError(null)
      feedbackErrorTimer.current = null
    }, 4500)
  }

  async function handleAsk() {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || loading) {
      return
    }

    setLoading(true)
    setError(null)
    setApprovalMessage('')
    resetFeedbackState()

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
    resetFeedbackState()
    setLoading(false)
  }

  function handleApprove() {
    setApprovalMessage('Approved (not sent - no delivery destination in this task)')
  }

  async function handleFeedback(rating: FeedbackRating) {
    if (!result || feedbackLocked) {
      return
    }

    setFeedbackSelection(rating)
    setFeedbackLocked(true)
    setFeedbackError(null)

    try {
      await submitFeedback({
        question: result.question,
        draft: result.draft,
        source_ids: result.source_ids,
        rating,
      })
    } catch (cause) {
      setFeedbackSelection(null)
      setFeedbackLocked(false)
      showFeedbackError(
        cause instanceof Error ? cause.message : 'Unable to submit feedback right now.',
      )
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <h1>Two-Step Research & Draft Reply Agent</h1>
          <p className="hero-summary">
            Retrieves grounded evidence from the help center, drafts a reply from it, and
            refuses to guess if nothing relevant is found. Nothing is sent without your
            approval.
          </p>
        </div>

        <div className="search-card">
          <label className="question-label" htmlFor="question">
            Support Question
          </label>
          <div className="question-row">
            <input
              id="question"
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Example: How do I update my profile picture?"
              aria-label="Question input"
            />
            <button type="button" onClick={handleAsk} disabled={loading || !question.trim()}>
              {loading ? 'Asking...' : 'Ask'}
            </button>
          </div>
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
          <div className="panel-header">
            <h2>Retrieved Evidence</h2>
            <span className="panel-kicker">Retrieval-first evidence trail</span>
          </div>
          {loading ? (
            <div className="skeleton-stack" aria-label="Loading retrieved evidence">
              <div className="skeleton-line skeleton-title" />
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
              <div className="skeleton-pill" />
            </div>
          ) : hasResult ? (
            result.retrieved_snippets.length > 0 ? (
              <div className="snippet-list">
                {result.retrieved_snippets.map((snippet) => (
                  <div key={snippet.id} className="snippet">
                    <div className="snippet-topline">
                      <h3>{snippet.title}</h3>
                      <span className="score">Score: {snippet.score.toFixed(3)}</span>
                    </div>
                    <p>{snippet.content}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-state">
                No relevant help content found in the knowledge base for this question.
              </p>
            )
          ) : (
            <p className="empty-state">
              No evidence retrieved yet.
              <br />
              <br />
              Ask a support question to search the knowledge base.
            </p>
          )}
        </article>

        <article
          className={`panel draft-panel ${hasResult && !result.grounded ? 'ungrounded' : ''}`}
          data-testid="draft-panel"
        >
          <div className="panel-header">
            <h2>Draft Reply</h2>
            <span className="panel-kicker">Grounded draft for human review</span>
          </div>
          {loading ? (
            <div className="skeleton-stack" aria-label="Loading draft reply">
              <div className="skeleton-line skeleton-title" />
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
            </div>
          ) : hasResult ? (
            <>
              {!result.grounded ? <div className="refusal-badge">Ungrounded / refusal</div> : null}
              <p className="draft-text">{result.draft}</p>
              <div className="feedback-row" aria-label="Draft feedback controls">
                <button
                  type="button"
                  className={`feedback-button thumbs-up${feedbackSelection === 'up' ? ' selected' : ''}`}
                  onClick={() => handleFeedback('up')}
                  disabled={feedbackLocked}
                  aria-pressed={feedbackSelection === 'up'}
                >
                  Thumbs up
                </button>
                <button
                  type="button"
                  className={`feedback-button thumbs-down${feedbackSelection === 'down' ? ' selected' : ''}`}
                  onClick={() => handleFeedback('down')}
                  disabled={feedbackLocked}
                  aria-pressed={feedbackSelection === 'down'}
                >
                  Thumbs down
                </button>
              </div>
              {feedbackError ? (
                <p className="inline-feedback-error" role="status" aria-live="polite">
                  {feedbackError}
                </p>
              ) : null}
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
            <p className="empty-state">
              No draft generated yet.
              <br />
              <br />
              Grounded replies will appear here after retrieval.
            </p>
          )}
        </article>

          <details className="how-this-works">
          <summary>How this works</summary>
          <div className="how-this-works-body">
            <p>
              Retrieval uses Pinecone semantic search with integrated inference, not a
              local embedding model. That keeps the knowledge base lookup grounded while
              staying lightweight for this small, static 32-snippet knowledge base.
            </p>
            <p>
              The score shown on each snippet is out of 1.0. Snippets below the minimum
              threshold are excluded entirely, which is why some questions return zero
              results.
            </p>
            <p>
              Approve does not send anything anywhere. There is no delivery destination in
              this task; it only confirms that a human reviewed and accepted the draft.
            </p>
            <p>
              The draft is generated only from the visible retrieved snippets above it. If a
              claim is not supported by a snippet you can see, it should not appear in the
              draft.
            </p>
          </div>
        </details>
      </section>
    </main>
  )
}

export default App
