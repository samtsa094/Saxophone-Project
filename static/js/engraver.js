(function () {
  const PITCH_CLASSES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"];
  const DURATION_SLOTS = [
    { slots: 16, vex: "w" },
    { slots: 12, vex: "hd" },
    { slots: 8, vex: "h" },
    { slots: 6, vex: "qd" },
    { slots: 4, vex: "q" },
    { slots: 3, vex: "8d" },
    { slots: 2, vex: "8" },
    { slots: 1, vex: "16" },
  ];
  const MEASURE_SLOTS = 16;
  const MEASURE_WIDTH = 260;
  const MEASURES_PER_LINE = 4;
  const ROW_HEIGHT = 160;

  function midiToVexKey(midiPitch) {
    const pitchClass = ((midiPitch % 12) + 12) % 12;
    const octave = Math.floor(midiPitch / 12) - 1;
    return `${PITCH_CLASSES[pitchClass]}/${octave}`;
  }

  function appendRestSlots(entries, startSlot, slots) {
    let remaining = slots;
    let cursor = startSlot;
    while (remaining > 0) {
      const measureRemaining = MEASURE_SLOTS - (cursor % MEASURE_SLOTS);
      const available = Math.min(remaining, measureRemaining);
      let chunkRemaining = available;
      for (const duration of DURATION_SLOTS) {
        while (chunkRemaining >= duration.slots) {
          entries.push({
            kind: "rest",
            startSlot: cursor,
            slots: duration.slots,
            vexDuration: `${duration.vex}r`,
          });
          cursor += duration.slots;
          chunkRemaining -= duration.slots;
          remaining -= duration.slots;
        }
      }
    }
    return cursor;
  }

  function normalizeMeasureEntries(entries, measureCount) {
    const normalized = [];
    for (let measureIndex = 0; measureIndex < measureCount; measureIndex += 1) {
      const measureStart = measureIndex * MEASURE_SLOTS;
      const measureEnd = measureStart + MEASURE_SLOTS;
      let cursor = measureStart;
      const measureEntries = entries
        .filter((entry) => (
          entry.startSlot < measureEnd
          && entry.startSlot + entry.slots > measureStart
        ))
        .sort((left, right) => left.startSlot - right.startSlot);

      for (const entry of measureEntries) {
        const entryStart = Math.max(measureStart, entry.startSlot);
        const entryEnd = Math.min(measureEnd, entry.startSlot + entry.slots);
        if (entryEnd <= cursor) {
          continue;
        }
        if (entryStart > cursor) {
          cursor = appendRestSlots(normalized, cursor, entryStart - cursor);
        }

        const available = entryEnd - cursor;
        if (available <= 0) {
          continue;
        }
        const clippedEntry = { ...entry, startSlot: cursor, slots: available };
        normalized.push(clippedEntry);
        cursor += available;
      }

      if (cursor < measureEnd) {
        cursor = appendRestSlots(normalized, cursor, measureEnd - cursor);
      }
    }
    return normalized;
  }

  function makeTimeline(scoreData) {
    const bpm = scoreData.bpm || 120;
    const beatSeconds = 60 / bpm;
    const sourceNotes = [...(scoreData.processed_notes || [])].sort(
      (left, right) => left.start - right.start || right.velocity - left.velocity
    );
    const strongestByOnset = new Map();
    for (const note of sourceNotes) {
      const onsetSlot = Math.max(0, Math.round(note.start / beatSeconds * 4));
      const current = strongestByOnset.get(onsetSlot);
      if (!current || note.velocity > current.note.velocity) {
        strongestByOnset.set(onsetSlot, { note, onsetSlot });
      }
    }

    const entries = [];
    let cursor = 0;
    for (const { note, onsetSlot } of strongestByOnset.values()) {
      if (onsetSlot < cursor) {
        continue;
      }
      if (onsetSlot > cursor) {
        cursor = appendRestSlots(entries, cursor, onsetSlot - cursor);
      }

      let remaining = Math.max(
        1,
        Math.round(note.duration / beatSeconds * 4)
      );
      let noteCursor = cursor;
      while (remaining > 0) {
        const measureRemaining = MEASURE_SLOTS - (noteCursor % MEASURE_SLOTS);
        const available = Math.min(remaining, measureRemaining);
        let chunkRemaining = available;
        for (const duration of DURATION_SLOTS) {
          while (chunkRemaining >= duration.slots) {
            entries.push({
              kind: "note",
              event: note,
              startSlot: noteCursor,
              slots: duration.slots,
              vexDuration: duration.vex,
            });
            noteCursor += duration.slots;
            chunkRemaining -= duration.slots;
            remaining -= duration.slots;
          }
        }
      }
      cursor = noteCursor;
    }

    const measureCount = Math.max(1, Math.ceil(cursor / MEASURE_SLOTS));
    const endSlot = measureCount * MEASURE_SLOTS;
    if (cursor < endSlot) {
      cursor = appendRestSlots(entries, cursor, endSlot - cursor);
    }
    const normalizedEntries = normalizeMeasureEntries(entries, measureCount);
    return { entries: normalizedEntries, measureCount, bpm: bpm, beatSeconds };
  }

  function makePolyphonicTimeline(scoreData) {
    const bpm = scoreData.bpm || 120;
    const beatSeconds = 60 / bpm;
    const sourceNotes = [...(scoreData.processed_notes || [])].sort(
      (left, right) => left.start - right.start || right.velocity - left.velocity
    );
    const groups = new Map();
    for (const note of sourceNotes) {
      const onsetSlot = Math.max(0, Math.round(note.start / beatSeconds * 4));
      if (!groups.has(onsetSlot)) {
        groups.set(onsetSlot, []);
      }
      groups.get(onsetSlot).push(note);
    }

    const onsets = [...groups.keys()].sort((left, right) => left - right);
    const entries = [];
    let cursor = 0;
    for (let index = 0; index < onsets.length; index += 1) {
      const onsetSlot = onsets[index];
      if (onsetSlot > cursor) {
        cursor = appendRestSlots(entries, cursor, onsetSlot - cursor);
      }
      const notes = groups.get(onsetSlot);
      notes.sort((left, right) => left.pitch - right.pitch);
      const nextOnset = onsets[index + 1];
      const longestDuration = Math.max(
        1,
        ...notes.map((note) => Math.round(note.duration / beatSeconds * 4))
      );
      const durationSlots = nextOnset === undefined
        ? longestDuration
        : Math.max(1, Math.min(longestDuration, nextOnset - onsetSlot));
      let noteCursor = onsetSlot;
      let remaining = durationSlots;
      while (remaining > 0) {
        const measureRemaining = MEASURE_SLOTS - (noteCursor % MEASURE_SLOTS);
        const available = Math.min(remaining, measureRemaining);
        let chunkRemaining = available;
        for (const duration of DURATION_SLOTS) {
          while (chunkRemaining >= duration.slots) {
            entries.push({
              kind: "note",
              events: notes,
              startSlot: noteCursor,
              slots: duration.slots,
              vexDuration: duration.vex,
            });
            noteCursor += duration.slots;
            chunkRemaining -= duration.slots;
            remaining -= duration.slots;
          }
        }
      }
      cursor = Math.max(cursor, onsetSlot + durationSlots);
    }

    const measureCount = Math.max(1, Math.ceil(cursor / MEASURE_SLOTS));
    const endSlot = measureCount * MEASURE_SLOTS;
    if (cursor < endSlot) {
      cursor = appendRestSlots(entries, cursor, endSlot - cursor);
    }
    const normalizedEntries = normalizeMeasureEntries(entries, measureCount);
    return { entries: normalizedEntries, measureCount, bpm, beatSeconds };
  }

  function renderSaxophoneScore(scoreData, genreStyle) {
    const container = document.getElementById("notation-canvas");
    const viewport = document.getElementById("score-viewport");
    const cursorElement = document.getElementById("timeline-cursor");
    container.replaceChildren(cursorElement);

    if (!window.Vex || !window.Vex.Flow) {
      container.appendChild(document.createTextNode(
        "Notation library could not be loaded. Check your internet connection and reload."
      ));
      throw new Error("VexFlow is unavailable.");
    }

    const timeline = scoreData.selected_track === "all_voices"
      ? makePolyphonicTimeline(scoreData)
      : makeTimeline(scoreData);
    const lineCount = Math.ceil(timeline.measureCount / MEASURES_PER_LINE);
    const width =
      16 + Math.min(timeline.measureCount, MEASURES_PER_LINE) * MEASURE_WIDTH;
    const height = 190 + (lineCount - 1) * ROW_HEIGHT;
    container.style.width = `${width}px`;
    container.style.minWidth = `${width}px`;

    const { Renderer, Stave, Voice, Formatter, StaveNote, StaveTie } = window.Vex.Flow;
    const allowRangeWarnings = scoreData.selected_track !== "all_voices";
    const renderer = new Renderer(container, Renderer.Backends.SVG);
    renderer.resize(width, height);
    const context = renderer.getContext();
    const notesByEvent = new Map();
    const segmentsByEvent = new Map();
    const noteAnchors = [];

    for (let measureIndex = 0; measureIndex < timeline.measureCount; measureIndex += 1) {
      const measureStart = measureIndex * MEASURE_SLOTS;
      const measureEnd = measureStart + MEASURE_SLOTS;
      const measureInLine = measureIndex % MEASURES_PER_LINE;
      const rowIndex = Math.floor(measureIndex / MEASURES_PER_LINE);
      const staveY = 35 + rowIndex * ROW_HEIGHT;
      const stave = new Stave(
        8 + measureInLine * MEASURE_WIDTH,
        staveY,
        MEASURE_WIDTH
      );
      if (measureInLine === 0) {
        stave.addClef("treble");
        if (measureIndex === 0) {
          stave.addTimeSignature("4/4");
        }
        const keySignature = scoreData.key_signature;
        if (keySignature) {
          stave.addKeySignature(keySignature);
        }
      }
      stave.setContext(context).draw();

      const measureEntries = timeline.entries.filter(
        (entry) => entry.startSlot >= measureStart && entry.startSlot < measureEnd
      );
      const voice = new Voice("4/4");
      voice.setMode(Voice.Mode.SOFT);
      const entryNotes = [];

      for (const entry of measureEntries) {
        const events = entry.events || [entry.event];
        const vexNote = entry.kind === "rest"
          ? new StaveNote({
            keys: ["b/4"],
            duration: entry.vexDuration,
            clef: "treble",
            type: "r",
          })
          : new StaveNote({
            keys: events.map((event) => midiToVexKey(event.pitch)),
            duration: entry.vexDuration,
            clef: "treble",
          });
        if (
          entry.kind === "note"
          && events.some((event) => event.shifted_up || event.shifted_down)
        ) {
          vexNote.setStyle({ fillStyle: "#F59E0B", strokeStyle: "#F59E0B" });
        }
        voice.addTickable(vexNote);
        entryNotes.push({ entry, vexNote });
      }

      new Formatter().joinVoices([voice]).formatToStave([voice], stave);
      voice.draw(context, stave);

      for (const { entry, vexNote } of entryNotes) {
        if (entry.kind !== "note") {
          continue;
        }
        const svgElement = vexNote.getSVGElement();
        const events = entry.events || [entry.event];
        events.forEach((scoreEvent, eventIndex) => {
          const ref = {
            id: scoreEvent.id,
            pitch: scoreEvent.pitch,
            playbackPitch: typeof scoreEvent.playbackPitch === "number"
              ? scoreEvent.playbackPitch
              : (typeof scoreEvent.original_pitch === "number"
                ? scoreEvent.original_pitch
                : scoreEvent.pitch),
            start: scoreEvent.start,
            duration: scoreEvent.duration,
            x: vexNote.getAbsoluteX(),
            rowTop: staveY - 11,
            element: svgElement,
            note: vexNote,
            chordIndex: eventIndex,
            shifted: scoreEvent.shifted_up || scoreEvent.shifted_down,
            altissimo: scoreEvent.pitch > 91,
          };
          if (allowRangeWarnings && ref.shifted && svgElement) {
            svgElement.classList.add("score-warning-note");
          } else if (allowRangeWarnings && ref.altissimo && svgElement) {
            svgElement.classList.add("score-altissimo-note");
          }
          if (svgElement && eventIndex === 0 && allowRangeWarnings) {
            const toggleOctave = () => window.toggleNoteOctave(scoreEvent.id);
            svgElement.setAttribute("tabindex", "0");
            svgElement.setAttribute("role", "button");
            svgElement.setAttribute(
              "aria-label",
              `MIDI pitch ${scoreEvent.pitch}; activate to toggle octave adjustment`
            );
            svgElement.style.cursor = "pointer";
            svgElement.addEventListener("click", toggleOctave);
            svgElement.addEventListener("keydown", (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleOctave();
              }
            });
          }
          if (!segmentsByEvent.has(scoreEvent.id)) {
            segmentsByEvent.set(scoreEvent.id, []);
          }
          segmentsByEvent.get(scoreEvent.id).push(ref);
          if (!notesByEvent.has(scoreEvent.id)) {
            notesByEvent.set(scoreEvent.id, ref);
            noteAnchors.push(ref);
          }
        });
      }
    }

    for (const segments of segmentsByEvent.values()) {
      segments.sort((left, right) => left.x - right.x);
      for (let index = 1; index < segments.length; index += 1) {
        if (segments[index - 1].rowTop !== segments[index].rowTop) {
          continue;
        }
        new StaveTie({
          first_note: segments[index - 1].note,
          last_note: segments[index].note,
          first_indices: [segments[index - 1].chordIndex],
          last_indices: [segments[index].chordIndex],
        }).setContext(context).draw();
      }
    }

    if (genreStyle === "Classical") {
      for (let index = 1; index < noteAnchors.length; index += 1) {
        const previous = noteAnchors[index - 1];
        const current = noteAnchors[index];
        if (
          previous.pitch === current.pitch
          && Math.abs(previous.start + previous.duration - current.start) < 0.001
          && previous.rowTop === current.rowTop
        ) {
          new StaveTie({
            first_note: previous.note,
            last_note: current.note,
            first_indices: [previous.chordIndex],
            last_indices: [current.chordIndex],
          }).setContext(context).draw();
        }
      }
    } else if (genreStyle === "Pop/Rock") {
      noteAnchors.forEach((note, index) => {
        if (note.pitch <= 80) {
          return;
        }
        const previousPitch = index > 0 ? noteAnchors[index - 1].pitch : note.pitch;
        const label = document.createElement("span");
        label.className = "score-label";
        label.textContent = note.pitch > previousPitch ? "Scoop" : "Fall";
        label.style.left = `${note.x + 8}px`;
        label.style.top = "8px";
        container.appendChild(label);
      });
    }

    noteAnchors.sort((left, right) => left.start - right.start);
    const totalDuration = Math.max(
      0,
      ...noteAnchors.map((note) => note.start + note.duration)
    );
    window.scoreRenderData = {
      notes: noteAnchors,
      tiedSegments: [...segmentsByEvent.values()].flat(),
      totalDuration,
      width,
      lineCount,
      beatSeconds: timeline.beatSeconds,
    };
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
    cursorElement.hidden = true;
    return window.scoreRenderData;
  }

  window.renderSaxophoneScore = renderSaxophoneScore;
})();
