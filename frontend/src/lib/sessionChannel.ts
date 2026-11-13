const CHANNEL_NAME = 'endurain:session'
const SESSION_ENDED = 'session-ended'

let channel: BroadcastChannel | null | undefined

/**
 * Opens this tab's channel on first use.
 *
 * A tab never receives its own messages, so one channel serves both directions.
 *
 * @returns The channel, or `null` when the browser has no BroadcastChannel.
 */
function getChannel(): BroadcastChannel | null {
  if (channel === undefined) {
    channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CHANNEL_NAME)
  }
  return channel
}

/** Tells the other tabs of this browser that the session ended here. No-op without BroadcastChannel. */
export function broadcastSessionEnded(): void {
  getChannel()?.postMessage(SESSION_ENDED)
}

/**
 * Registers the handler for a session that ended in another tab. Call once during bootstrap; a
 * second call replaces the first. No-op without BroadcastChannel.
 *
 * @param handler - Called when another tab ends the session.
 */
export function onSessionEndedElsewhere(handler: () => void): void {
  const target = getChannel()
  if (target) {
    target.onmessage = (event: MessageEvent<unknown>) => {
      if (event.data === SESSION_ENDED) {
        handler()
      }
    }
  }
}
