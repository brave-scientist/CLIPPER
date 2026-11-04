export type Step = 'add' | 'pick' | 'save';

export type AspectRatio = '9:16' | '1:1' | '4:3';

export interface ClipScores {
  hook: number;
  pacing: number;
  trend: number;
  total: number;
}

export interface Clip {
  id: string;
  start: number;
  end: number;
  title: string;
  reason: string;
  scores: ClipScores;
  thumbnailUrl?: string;
}

export type CaptionStyle = 'bold_pop' | 'karaoke' | 'clean' | 'none';

export interface FancyOptions {
  captions: CaptionStyle | boolean;
  music: boolean;
  removeSilence: boolean;
  remove_fillers?: boolean;
  sfx?: boolean;
  broll?: boolean;
  smart_reframe?: boolean;
}

export interface WordTiming {
  word: string;
  start: number;
  end: number;
}
