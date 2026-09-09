/** Shared closed disclosure for both the host and a room member's answer. */
export function createTraceDisclosure() {
  const details = document.createElement("details");
  details.className = "answer-trace";
  const summary = document.createElement("summary");
  summary.className = "trace-toggle";
  const label = document.createElement("span");
  label.textContent = "思考轨迹";
  const count = document.createElement("span");
  count.className = "trace-count";
  const chevron = document.createElement("span");
  chevron.className = "trace-chevron";
  chevron.textContent = "⌄";
  chevron.setAttribute("aria-hidden", "true");
  summary.append(label, count, chevron);
  const body = document.createElement("div");
  body.className = "trace-content";
  details.append(summary, body);
  return { details, body, count };
}

/** Move process rows into the answer they precede without cloning them:
 * tool results and compaction still address the original event nodes. */
export function createAnswerTraces(container) {
  const groups = new Set();
  let pending = null;

  function refresh(group) {
    group.count.textContent = String(group.body.childElementCount);
  }

  function createGroup() {
    const group = { ...createTraceDisclosure(), answer: null };
    group.details.classList.add("trace-pending");
    container().append(group.details);
    groups.add(group);
    return group;
  }

  return {
    /** Keep pending rows connected so a later tool result can update its call. */
    add(node) {
      pending ??= createGroup();
      pending.body.append(node);
      refresh(pending);
    },

    /** The disclosure is the last item inside the answer's bubble. */
    attach(answer) {
      if (pending === null) return;
      const bubble = answer.querySelector(".bubble");
      if (bubble === null) return;
      bubble.append(pending.details);
      pending.details.classList.remove("trace-pending");
      pending.answer = answer;
      pending = null;
    },

    /** Unanswered/interrupted traces remain accessible, but never cross turns. */
    boundary() { pending = null; },

    /** Compaction may replace an answer while preserving earlier process rows. */
    beforeRemove(doomed) {
      for (const group of groups) {
        if (group.answer !== null && doomed.has(group.answer)) {
          group.answer.before(group.details);
          group.details.classList.add("trace-pending");
          group.answer = null;
        }
      }
    },

    /** Drop empty disclosures after their individual event nodes are removed. */
    prune() {
      for (const group of groups) {
        if (group.body.childElementCount === 0) {
          group.details.remove();
          groups.delete(group);
          if (pending === group) pending = null;
        } else refresh(group);
      }
    },

    reset() { groups.clear(); pending = null; },
  };
}
