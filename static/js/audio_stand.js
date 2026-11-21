(function () {
  const playButton = document.getElementById("play-toggle");
  const tempoSelect = document.getElementById("tempo-scale");
  const metronomeToggle = document.getElementById("metronome-enabled");
  const viewport = document.getElementById("score-viewport");
  const cursor = document.getElementById("timeline-cursor");
  const status = document.getElementById("playback-status");
  const warningButton = document.getElementById("range-warning-open");
  const warningDialog = document.getElementById("range-warning-dialog");
  const scoreSummary = document.getElementById("score-summary");
  const voiceTabs = [...document.querySelectorAll("[data-track-id]")];
  let audioContext;
  let scheduledNodes = [];
  let animationFrame = null;
  let playbackPosition = 0;
  let playbackStartTime = 0;
  let playbackSpeed = 1;
  let playing = false;
  let lastAutoScrollX = 0;
  let lastAutoScrollRowTop = null;

  function getAudioContext() {
    if (!audioContext) {
      const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextConstructor) {
        throw new Error("Web Audio is not supported in this browser.");
      }
      audioContext = new AudioContextConstructor();
    }
    return audioContext;
  }

  function stopScheduledAudio() {
    for (const node of scheduledNodes) {
      try {
        node.stop();
      } catch (error) {
        if (error.name !== "InvalidStateError") {
          throw error;
        }
      }
    }
    scheduledNodes = [];
  }

  function scheduleTone(context, note, startTime, duration) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const noteStart = Math.max(context.currentTime, startTime);
    const noteEnd = Math.max(noteStart + 0.04, startTime + duration);
    const lowPitchThreshold = 62;
    const lowPitchFloor = 44;
    const lowPitchAmount = Math.max(
      0,
      Math.min(
        1,
        (lowPitchThreshold - note.playbackPitch)
          / (lowPitchThreshold - lowPitchFloor)
      )
    );
    const peakGain = 0.12 + lowPitchAmount * 0.68;
    oscillator.type = "sine";
    oscillator.frequency.value = 440 * Math.pow(2, (note.playbackPitch - 69) / 12);
    gain.gain.setValueAtTime(0.0001, noteStart);
    gain.gain.linearRampToValueAtTime(peakGain, noteStart + 0.01);
    gain.gain.setValueAtTime(peakGain, Math.max(noteStart + 0.02, noteEnd - 0.015));
    gain.gain.linearRampToValueAtTime(0.0001, noteEnd);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(noteStart);
    oscillator.stop(noteEnd + 0.01);
    scheduledNodes.push(oscillator);
  }

  function scheduleMetronome(context, startTime, playbackPosition, totalDuration, speed) {
    if (!metronomeToggle.checked) {
      return;
    }
    const beatSeconds = window.scoreRenderData.beatSeconds;
    const tolerance = 1e-6;
    const firstBeat = Math.max(
      0,
      playbackPosition < tolerance
        ? 0
        : Math.floor(playbackPosition / beatSeconds)
          + (Math.abs(playbackPosition % beatSeconds) < tolerance ? 0 : 1)
    );
    for (let beat = firstBeat; beat * beatSeconds < totalDuration; beat += 1) {
      const click = context.createOscillator();
      const gain = context.createGain();
      const offset = Math.max(
        0,
        beat * beatSeconds - playbackPosition
      );
      const clickTime = startTime + offset / speed;
      click.frequency.value = beat % 4 === 0 ? 1200 : 850;
      gain.gain.setValueAtTime(0.08, clickTime);
      gain.gain.exponentialRampToValueAtTime(0.001, clickTime + 0.035);
      click.connect(gain);
      gain.connect(context.destination);
      click.start(clickTime);
      click.stop(clickTime + 0.04);
      scheduledNodes.push(click);
    }
  }

  function schedulePlayback(context) {
    stopScheduledAudio();
    const speed = Number(tempoSelect.value);
    playbackSpeed = speed;
    const startTime = context.currentTime + 0.04;
    const remaining = window.scoreRenderData.notes.filter(
      (note) => note.start + note.duration > playbackPosition
    );
    for (const note of remaining) {
      const offset = Math.max(0, note.start - playbackPosition);
      const elapsedInNote = Math.max(0, playbackPosition - note.start);
      const duration = Math.max(0.06, note.duration - elapsedInNote) / speed;
      scheduleTone(context, note, startTime + offset / speed, duration);
    }
    scheduleMetronome(
      context,
      startTime,
      playbackPosition,
      window.scoreRenderData.totalDuration,
      speed
    );
    playbackStartTime = startTime - playbackPosition / speed;
  }

  function setActiveNote(note) {
    let activeElement = note ? note.element : null;
    if (note) {
      const activeSegment = (window.scoreRenderData.tiedSegments || []).find(
        (segment) =>
          segment.id === note.id
          && playbackPosition >= segment.start
          && playbackPosition < segment.start + segment.duration
      );
      if (activeSegment && activeSegment.element) {
        activeElement = activeSegment.element;
      }
    }
    for (const renderedNote of [
      ...window.scoreRenderData.notes,
      ...(window.scoreRenderData.tiedSegments || []),
    ]) {
      if (renderedNote.element) {
        renderedNote.element.classList.toggle(
          "score-active-note",
          renderedNote.element === activeElement
        );
      }
    }
  }

  function positionAt(time) {
    const notes = window.scoreRenderData.notes;
    if (notes.length === 0) {
      return { x: 0, rowTop: 24 };
    }
    const nextIndex = notes.findIndex((note) => note.start > time);
    const previous = nextIndex === -1 ? notes[notes.length - 1] : notes[Math.max(0, nextIndex - 1)];
    const next = nextIndex === -1 ? previous : notes[nextIndex];
    if (
      previous === next
      || next.start <= previous.start
      || next.rowTop !== previous.rowTop
    ) {
      return { x: previous.x, rowTop: previous.rowTop };
    }
    const fraction = Math.max(0, Math.min(1, (time - previous.start) / (next.start - previous.start)));
    return {
      x: previous.x + (next.x - previous.x) * fraction,
      rowTop: previous.rowTop,
    };
  }

  function animate() {
    if (!playing) {
      return;
    }
    const currentTime = Math.max(
      0,
      (getAudioContext().currentTime - playbackStartTime) * playbackSpeed
    );
    playbackPosition = Math.min(currentTime, window.scoreRenderData.totalDuration);
    const activeNote = window.scoreRenderData.notes.find(
      (note) => playbackPosition >= note.start && playbackPosition < note.start + note.duration
    );
    setActiveNote(activeNote);
    const position = positionAt(playbackPosition);
    cursor.style.left = `${position.x}px`;
    cursor.style.top = `${position.rowTop}px`;
    cursor.hidden = false;

    const viewportX = position.x - viewport.scrollLeft;
    const rowChanged = position.rowTop !== lastAutoScrollRowTop;
    if (rowChanged) {
      lastAutoScrollRowTop = position.rowTop;
      lastAutoScrollX = position.x;
    }
    const needsVerticalScroll =
      rowChanged
      && (
        position.rowTop - viewport.scrollTop < 16
        || position.rowTop + 118 > viewport.scrollTop + viewport.clientHeight - 16
      );
    const needsRowReset = rowChanged && position.x < viewport.scrollLeft;
    const needsHorizontalScroll =
      viewportX > viewport.clientWidth * 0.75
      && position.x > lastAutoScrollX;
    if (needsVerticalScroll || needsHorizontalScroll || needsRowReset) {
      lastAutoScrollX = position.x;
      viewport.scrollTo({
        left: Math.max(
          0,
          position.x - (rowChanged ? viewport.clientWidth * 0.15 : viewport.clientWidth * 0.5)
        ),
        top: needsVerticalScroll
          ? Math.max(0, position.rowTop - viewport.clientHeight * 0.25)
          : viewport.scrollTop,
        behavior: "smooth",
      });
    }

    if (playbackPosition >= window.scoreRenderData.totalDuration) {
      stopPlayback(true);
      return;
    }
    animationFrame = window.requestAnimationFrame(animate);
  }

  function stopPlayback(reset) {
    playing = false;
    if (animationFrame !== null) {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
    stopScheduledAudio();
    if (reset) {
      playbackPosition = 0;
      cursor.hidden = true;
      setActiveNote(null);
    }
    playButton.textContent = "Play";
    playButton.setAttribute("aria-pressed", "false");
    status.textContent = reset ? "Playback complete." : "Playback paused.";
  }

  function updateRangeWarnings() {
    if (!globalScoreData || !globalScoreData.processed_notes) {
      return;
    }
    const adjustedNotes = globalScoreData.processed_notes.filter(
      (note) => note.shifted_up || note.shifted_down
    );
    const warningButtonElement = document.getElementById("range-warning-open");
    const warningAlert = document.getElementById("range-alert");
    const warningCount = document.getElementById("range-alert-count");
    const warningPhraseCount = document.getElementById("range-alert-phrases");
    const adjustedCount = document.getElementById("adjusted-notes-count");
    const warningNone = document.getElementById("range-warning-none");
    const detailsNone = document.getElementById("range-details-none");
    const warningLists = [
      document.getElementById("range-warning-list"),
      document.getElementById("range-details-list"),
    ];

    const phraseGroups = new Map();
    const warningEntries = [];
    for (const note of adjustedNotes) {
      const direction = note.pitch > note.transposed_pitch ? "up" : "down";
      if (note.phrase_shifted_up || note.phrase_shifted_down) {
        const key = `${note.phrase_id}:${direction}`;
        if (!phraseGroups.has(key)) {
          phraseGroups.set(key, {
            phraseId: note.phrase_id,
            direction,
            count: 0,
            noteId: note.id,
          });
        }
        phraseGroups.get(key).count += 1;
      } else {
        warningEntries.push({
          noteId: note.id,
          message: `Note MIDI ${note.transposed_pitch} shifted ${direction} to ${note.pitch}.`,
        });
      }
    }
    for (const phrase of phraseGroups.values()) {
      warningEntries.push({
        noteId: phrase.noteId,
        message:
          `Phrase ${Number(phrase.phraseId) + 1} shifted ${phrase.direction} ` +
          `across ${phrase.count} note${phrase.count === 1 ? "" : "s"}.`,
      });
    }
    warningEntries.sort((left, right) => left.message.localeCompare(right.message));
    const affectedPhrases = new Set(
      adjustedNotes.map((note) => note.phrase_id)
    ).size;

    if (warningButtonElement) {
      warningButtonElement.disabled = warningEntries.length === 0;
      warningButtonElement.textContent = `Range warnings (${warningEntries.length})`;
    }
    if (warningAlert) warningAlert.hidden = warningEntries.length === 0;
    if (warningCount) warningCount.textContent = String(adjustedNotes.length);
    if (warningPhraseCount) warningPhraseCount.textContent = String(affectedPhrases);
    if (adjustedCount) adjustedCount.textContent = String(adjustedNotes.length);
    if (warningNone) warningNone.hidden = adjustedNotes.length > 0;
    if (detailsNone) detailsNone.hidden = adjustedNotes.length > 0;

    for (const list of warningLists) {
      if (!list) continue;
      list.hidden = warningEntries.length === 0;
      list.replaceChildren(...warningEntries.map((entry) => {
        const item = document.createElement("li");
        item.textContent = entry.message;
        item.tabIndex = 0;
        item.setAttribute("role", "button");
        item.title = "Jump to this range adjustment in the score.";
        item.addEventListener("click", () => focusRangeNote(entry.noteId));
        item.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            focusRangeNote(entry.noteId);
          }
        });
        return item;
      }));
    }
  }

  function focusRangeNote(noteId) {
    const note = window.scoreRenderData.notes.find(
      (candidate) => candidate.id === noteId
    );
    if (!note || !note.element) {
      return;
    }
    viewport.scrollTo({
      left: Math.max(0, note.x - viewport.clientWidth * 0.5),
      top: Math.max(0, note.rowTop - viewport.clientHeight * 0.25),
      behavior: "smooth",
    });
    note.element.classList.add("score-range-focus");
    window.setTimeout(() => note.element.classList.remove("score-range-focus"), 900);
  }

  function switchVoice(trackId) {
    const trackData = globalScoreData.tracks && globalScoreData.tracks[trackId];
    if (!trackData || globalScoreData.selected_track === trackId) {
      return;
    }

    const wasPlaying = playing;
    if (wasPlaying) {
      playbackPosition = Math.max(
        0,
        (getAudioContext().currentTime - playbackStartTime) * playbackSpeed
      );
      stopScheduledAudio();
    }
    const tracks = globalScoreData.tracks;
    Object.assign(globalScoreData, trackData);
    globalScoreData.tracks = tracks;
    globalScoreData.selected_track = trackId;
    lastAutoScrollX = 0;
    lastAutoScrollRowTop = null;
    playbackPosition = Math.min(
      playbackPosition,
      Math.max(0, ...globalScoreData.processed_notes.map(
        (note) => note.start + note.duration
      ))
    );
    voiceTabs.forEach((tab) => {
      tab.setAttribute("aria-selected", String(tab.dataset.trackId === trackId));
    });
    scoreSummary.textContent =
      `${globalScoreData.summary_stats.total_notes} notes · ${globalScoreData.bpm} BPM`;
    updateRangeWarnings();
    window.renderSaxophoneScore(globalScoreData, globalGenreStyle);

    if (wasPlaying) {
      schedulePlayback(getAudioContext());
      status.textContent = "Playing synthesized concert-pitch reference.";
    } else {
      status.textContent = `Showing ${globalScoreData.track_labels[trackId]}.`;
    }
  }

  window.toggleNoteOctave = (noteId) => {
    const note = globalScoreData.processed_notes.find(
      (candidate) => candidate.id === noteId
    );
    if (!note) {
      status.textContent = "Could not find the selected score note.";
      return;
    }

    const profile = globalScoreData.profile;
    const lowestPitch = profile.horn_type === "Baritone" && profile.has_low_a ? 57 : 58;
    const highestPitch = profile.skill_level === "Advanced"
      ? profile.altissimo_enabled ? 96 : 91
      : 89;

    stopPlayback(false);
    if (note.manual_override) {
      note.pitch = note.range_adjusted_pitch;
      note.manual_override = false;
    } else {
      const candidates = note.range_adjusted_pitch > note.transposed_pitch
        ? [note.range_adjusted_pitch - 12, note.range_adjusted_pitch + 12]
        : note.range_adjusted_pitch < note.transposed_pitch
          ? [note.range_adjusted_pitch + 12, note.range_adjusted_pitch - 12]
          : [note.range_adjusted_pitch + 12, note.range_adjusted_pitch - 12];
      const alternatePitch = candidates.find(
        (pitch) => pitch >= lowestPitch && pitch <= highestPitch
      );
      if (alternatePitch === undefined) {
        status.textContent = "No alternate octave fits the selected range.";
        return;
      }
      note.pitch = alternatePitch;
      note.manual_override = true;
    }

    const pitchDifference = note.pitch - note.range_adjusted_pitch;
    note.playbackPitch = typeof note.original_pitch === "number"
      ? note.original_pitch + pitchDifference
      : note.pitch;
    note.shifted_up = note.pitch > note.transposed_pitch;
    note.shifted_down = note.pitch < note.transposed_pitch;
    updateRangeWarnings();
    window.renderSaxophoneScore(globalScoreData, globalGenreStyle);
    status.textContent = note.manual_override
      ? `Note ${note.id} adjusted to MIDI ${note.pitch} for this view. Click again to revert.`
      : `Note ${note.id} restored to MIDI ${note.pitch}.`;
  };

  async function startPlayback() {
    const rendered = window.scoreRenderData;
    if (!rendered || rendered.notes.length === 0) {
      status.textContent = "There are no notes to play.";
      return;
    }
    const context = getAudioContext();
    await context.resume();
    if (playbackPosition >= rendered.totalDuration) {
      playbackPosition = 0;
    }
    schedulePlayback(context);
    playing = true;
    playButton.textContent = "Pause";
    playButton.setAttribute("aria-pressed", "true");
    status.textContent = "Playing synthesized concert-pitch reference.";
    animationFrame = window.requestAnimationFrame(animate);
  }

  playButton.addEventListener("click", () => {
    if (playing) {
      playbackPosition = Math.max(
        0,
        (getAudioContext().currentTime - playbackStartTime) * playbackSpeed
      );
      stopPlayback(false);
    } else {
      startPlayback().catch((error) => {
        status.textContent = error.message;
      });
    }
  });

  warningButton.addEventListener("click", () => {
    if (typeof warningDialog.showModal === "function") {
      warningDialog.showModal();
    }
  });

  tempoSelect.addEventListener("change", () => {
    if (playing) {
      playbackPosition = Math.max(
        0,
        (getAudioContext().currentTime - playbackStartTime) * playbackSpeed
      );
      schedulePlayback(getAudioContext());
    }
  });

  metronomeToggle.addEventListener("change", () => {
    if (playing) {
      playbackPosition = Math.max(
        0,
        (getAudioContext().currentTime - playbackStartTime) * playbackSpeed
      );
      schedulePlayback(getAudioContext());
    }
  });

  voiceTabs.forEach((tab) => {
    tab.addEventListener("click", () => switchVoice(tab.dataset.trackId));
  });

  window.addEventListener("beforeunload", () => {
    stopScheduledAudio();
    if (audioContext) {
      audioContext.close();
    }
  });

  try {
    updateRangeWarnings();
    window.renderSaxophoneScore(globalScoreData, globalGenreStyle);
  } catch (error) {
    console.error("Could not render the score:", error);
    status.textContent = error.message;
  }
})();
