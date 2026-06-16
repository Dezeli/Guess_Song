declare namespace YT {
  type PlayerVars = {
    controls?: 0 | 1;
    disablekb?: 0 | 1;
    modestbranding?: 0 | 1;
    playsinline?: 0 | 1;
    rel?: 0 | 1;
    start?: number;
  };

  type PlayerOptions = {
    videoId?: string;
    playerVars?: PlayerVars;
    events?: {
      onReady?: () => void;
    };
  };

  class Player {
    constructor(element: HTMLElement, options: PlayerOptions);
    cueVideoById(options: { videoId: string; startSeconds: number }): void;
    loadVideoById(options: { videoId: string; startSeconds: number }): void;
    playVideo(): void;
    stopVideo(): void;
    unMute(): void;
  }
}

interface Window {
  YT: typeof YT;
  onYouTubeIframeAPIReady?: () => void;
}
