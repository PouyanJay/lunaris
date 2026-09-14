import { useCallback, useState } from "react";
import type { LiveSession } from "../../../lib/liveSession";
import type { SimExchange } from "../../../lib/simContract";
import type { VoiceSource } from "../../../lib/voice/types";

/** Only persisted tutor/reaction identities become speech sources; recording always names a turn. */
export function useSessionVoiceSources(session: LiveSession | null) {
  const standing = session?.turns.at(-1);
  const sourceKey = JSON.stringify([session?.sessionId, standing?.seq, standing?.runId]);
  const [reaction, setReaction] = useState<{ sourceKey: string; sequence: number } | null>(null);
  const runId = standing?.runId;
  const onExchange = useCallback(
    (exchange: SimExchange) => {
      if (exchange.event.instanceId !== runId) return;
      setReaction({ sourceKey, sequence: exchange.event.sequence });
    },
    [sourceKey, runId],
  );
  const readable =
    standing &&
    standing.answer === null &&
    session?.status !== "warming" &&
    session?.status !== "abandoned";
  const source: VoiceSource | null = readable
    ? { turnSeq: standing.seq, runId: standing.runId }
    : null;
  const sequence = Math.max(
    standing?.simExchanges?.at(-1)?.event.sequence ?? 0,
    reaction?.sourceKey === sourceKey ? reaction.sequence : 0,
  );
  const speechSource = source && sequence ? { ...source, exchangeSequence: sequence } : source;
  return {
    answerSource: session?.status === "active" || session?.status === "placing" ? source : null,
    speechSource,
    speechKind: sequence ? ("simulator" as const) : ("tutor" as const),
    onExchange,
  };
}
