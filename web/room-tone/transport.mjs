// Native playback only. A pending selection owns its requested clock position;
// reading the freshly reset element during another tap would lose that position.
export class MediaTransport {
  constructor({video, audio, onChange = () => {}, onProblem = () => {}}) {
    this.video = video;
    this.audio = audio;
    this.onChange = onChange;
    this.onProblem = onProblem;
    this.generation = 0;
    this.playRequest = 0;
    this.changingSource = false;
    this.selection = null;
    this.active = null;
    this.position = 0;
    this.loading = false;
    this.wantsPlay = false;
    this.problem = null;
    this.removeLoadListeners = () => {};
    for (const element of [video, audio]) {
      for (const event of ['timeupdate', 'seeking', 'play', 'playing', 'pause', 'ended']) {
        element.addEventListener(event, () => this.nativeEvent(element, event));
      }
    }
  }

  target(selection) { return selection.type.startsWith('video/') ? this.video : this.audio; }

  adopt(selection) {
    this.selection = selection;
    this.active = this.target(selection);
    this.position = Number.isFinite(this.active.currentTime) ? this.active.currentTime : 0;
    this.wantsPlay = !this.active.paused;
    this.loading = false;
    this.notify();
  }

  snapshot() {
    const duration = Number.isFinite(this.active?.duration) ? this.active.duration : (this.selection?.duration || 112);
    const time = this.loading ? this.position : (Number.isFinite(this.active?.currentTime) ? this.active.currentTime : this.position);
    return {selection: this.selection, time, duration, sourceTime: time + (this.selection?.sourceStart || 0),
      loading: this.loading, wantsPlay: this.wantsPlay, problem: this.problem,
      playing: !!this.active && !this.active.paused && !this.loading};
  }

  notify() { this.onChange(this.snapshot()); }

  nativeEvent(element, event) {
    if (element !== this.active) return;
    if (event === 'play' || event === 'playing') {
      this.wantsPlay = true;
      if (event === 'playing') this.problem = null;
      (element === this.video ? this.audio : this.video).pause();
    }
    // A real native Pause still cancels playback while metadata is pending.
    // Ignore load()-related pauses and stale queued pause events after Play.
    if ((event === 'pause' || event === 'ended') && element.paused && !this.changingSource) {
      this.wantsPlay = false;
      this.playRequest++;
    }
    // load() time events must not replace the pending comparison clock.
    if (!this.loading) {
      if (Number.isFinite(element.currentTime)) this.position = element.currentTime;
    }
    this.notify();
  }

  use(selection, {preserve = true, play = this.wantsPlay} = {}) {
    const before = this.snapshot();
    const sameClock = this.selection?.clock === selection.clock;
    const requested = preserve && sameClock && !this.active?.ended ? before.time : 0;
    const token = ++this.generation;
    this.playRequest++;
    this.removeLoadListeners();
    this.loading = true;
    this.position = requested;
    this.wantsPlay = play;
    this.problem = null;
    this.selection = selection;
    this.active = this.target(selection);
    this.changingSource = true;
    this.video.pause();
    this.audio.pause();
    const element = this.active;
    const onMetadata = () => {
      if (token !== this.generation || element !== this.active) return;
      const end = Number.isFinite(element.duration) ? element.duration : selection.duration;
      const point = Math.max(0, Math.min(this.position, Math.max(0, end - 0.05)));
      try { element.currentTime = point; }
      catch {
        this.fail('SeekError', 'This file loaded, but its position could not be restored. Use the native seek control or open the file directly.', token);
        return;
      }
      this.position = point;
      this.loading = false;
      this.notify();
    };
    const onError = () => {
      if (token !== this.generation || !element.error) return;
      this.fail(`MediaError${element.error.code}`, 'This media file could not load. Open the file directly, or choose another version.', token);
    };
    element.addEventListener('loadedmetadata', onMetadata);
    element.addEventListener('error', onError);
    this.removeLoadListeners = () => {
      element.removeEventListener('loadedmetadata', onMetadata);
      element.removeEventListener('error', onError);
    };
    element.src = selection.url;
    element.load();
    this.changingSource = false;
    this.notify();
    // This call stays in the actual click handler. Waiting for loadedmetadata
    // before play() would lose the reliable user-gesture path in some browsers.
    if (play) this.playNative(token);
  }

  fail(code, message, token) {
    if (token !== this.generation) return;
    // A playback-policy rejection does not abort the media's metadata load.
    // Keep the pending clock until that load completes or another tap replaces it.
    if (code !== 'NotAllowedError') this.loading = false;
    this.wantsPlay = false;
    this.problem = {code, message, url: this.selection.url};
    this.onProblem(this.problem);
    this.notify();
  }

  playNative(token = this.generation) {
    if (!this.active) return;
    const element = this.active;
    const request = ++this.playRequest;
    this.wantsPlay = true;
    let promise;
    try { promise = element.play(); }
    catch (error) { this.playRejected(error, token, request); return; }
    if (promise?.then) promise.then(() => {
      if (token !== this.generation || request !== this.playRequest) return;
      this.wantsPlay = !element.paused;
      this.problem = null;
      this.notify();
    }, error => this.playRejected(error, token, request));
  }

  playRejected(error, token, request) {
    if (token !== this.generation || request !== this.playRequest) return;
    if (error.name === 'AbortError') {
      this.wantsPlay = false;
      this.notify();
      return;
    }
    const message = error.name === 'NotAllowedError'
      ? 'Tap Play on the native player controls to begin. Your browser did not allow the automatic restart.'
      : 'This file could not play. Open the file directly, or choose another version.';
    this.fail(error.name || 'PlaybackError', message, token);
  }

  play() { this.problem = null; this.playNative(); }
  pause() { this.playRequest++; this.wantsPlay = false; this.active?.pause(); this.notify(); }
  restart() {
    this.position = 0;
    if (this.active && !this.loading) this.active.currentTime = 0;
    this.play();
  }
}
