import type { SessionAction, SessionSnapshot } from '../state/tableStore'

async function readJson(response: Response) {
  const payload = (await response.json()) as { error?: string }
  if (!response.ok) {
    throw new Error(payload.error ?? `Request failed with ${response.status}`)
  }
  return payload
}

export async function createSession(): Promise<SessionSnapshot> {
  const response = await fetch('/api/session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  })
  return (await readJson(response)) as SessionSnapshot
}

export async function getSession(sessionId: string): Promise<SessionSnapshot> {
  const response = await fetch(`/api/session/${sessionId}`)
  return (await readJson(response)) as SessionSnapshot
}

export async function submitSessionAction(
  sessionId: string,
  action: SessionAction,
): Promise<SessionSnapshot> {
  const response = await fetch(`/api/session/${sessionId}/action`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ action }),
  })
  return (await readJson(response)) as SessionSnapshot
}

export async function continueSession(sessionId: string): Promise<SessionSnapshot> {
  const response = await fetch(`/api/session/${sessionId}/continue`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  })
  return (await readJson(response)) as SessionSnapshot
}
