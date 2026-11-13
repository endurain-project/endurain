import { afterEach, describe, expect, it, vi } from 'vitest'

/** Loads a fresh module, since it keeps one channel per tab for its lifetime. */
async function loadChannel(): Promise<typeof import('@/lib/sessionChannel')> {
  vi.resetModules()
  return import('@/lib/sessionChannel')
}

/** Minimal in-memory BroadcastChannel: a message reaches every other instance of the same name. */
class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = []
  onmessage: ((event: { data: unknown }) => void) | null = null

  constructor(readonly name: string) {
    FakeBroadcastChannel.instances.push(this)
  }

  postMessage(data: unknown): void {
    for (const other of FakeBroadcastChannel.instances) {
      if (other !== this && other.name === this.name) {
        other.onmessage?.({ data })
      }
    }
  }

  close(): void {
    FakeBroadcastChannel.instances = FakeBroadcastChannel.instances.filter((c) => c !== this)
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  FakeBroadcastChannel.instances = []
})

describe('sessionChannel', () => {
  it('tells a subscribed tab that the session ended in another tab', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const { onSessionEndedElsewhere } = await loadChannel()
    const handler = vi.fn<() => void>()
    onSessionEndedElsewhere(handler)

    new FakeBroadcastChannel('endurain:session').postMessage('session-ended')

    expect(handler).toHaveBeenCalledOnce()
  })

  it('reaches the other tabs when this tab broadcasts, but not this tab', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const { broadcastSessionEnded, onSessionEndedElsewhere } = await loadChannel()
    const here = vi.fn<() => void>()
    const elsewhere = vi.fn<() => void>()
    onSessionEndedElsewhere(here)
    const otherTab = new FakeBroadcastChannel('endurain:session')
    otherTab.onmessage = elsewhere

    broadcastSessionEnded()

    expect(elsewhere).toHaveBeenCalledOnce()
    expect(here).not.toHaveBeenCalled()
  })

  it('ignores a message that is not a session end', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const { onSessionEndedElsewhere } = await loadChannel()
    const handler = vi.fn<() => void>()
    onSessionEndedElsewhere(handler)

    new FakeBroadcastChannel('endurain:session').postMessage('something-else')

    expect(handler).not.toHaveBeenCalled()
  })

  it('does nothing when BroadcastChannel is unavailable', async () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    const { broadcastSessionEnded, onSessionEndedElsewhere } = await loadChannel()

    expect(() => broadcastSessionEnded()).not.toThrow()
    expect(() => onSessionEndedElsewhere(() => undefined)).not.toThrow()
  })
})
