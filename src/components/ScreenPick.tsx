import React, { useState, useEffect, useRef } from 'react';
import { Clip, FancyOptions } from '../types';
import {
  Play,
  Pause,
  Sparkles,
  SlidersHorizontal,
  Check,
  AlertCircle,
  RotateCcw,
  Search,
  Scissors,
  MessageSquareOff,
  Music,
  Volume2,
  Film,
  Video,
} from 'lucide-react';
import { fetchHighlights, getVideoThumbnailUrl, getVideoStreamUrl } from '../services/api';

type LengthMode = 'under30' | '30to60' | 'custom';

interface ScreenPickProps {
  videoId: string | null;
  videoDuration?: number | null;
  videoTitle?: string;
  videoUrl: string;
  clips: Clip[];
  setClips: React.Dispatch<React.SetStateAction<Clip[]>>;
  selectedClip: Clip | null;
  onSelectClip: (clip: Clip) => void;
  onNext: () => void;
  fancyOptions: FancyOptions;
  setFancyOptions: React.Dispatch<React.SetStateAction<FancyOptions>>;
}

interface ClipThumbnailProps {
  videoId: string;
  clip: Clip;
  isCurrentlyPlaying: boolean;
  onPlayClick: (e: React.MouseEvent) => void;
}

const ClipThumbnail: React.FC<ClipThumbnailProps> = ({
  videoId,
  clip,
  isCurrentlyPlaying,
  onPlayClick,
}) => {
  const [loaded, setLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Request the frame from the middle of the clip (start + (end-start)/2)
  const middleSec = Math.max(0, clip.start + (clip.end - clip.start) / 2);
  const thumbnailUrl = getVideoThumbnailUrl(videoId, middleSec);

  return (
    <div className="relative w-28 h-32 shrink-0 rounded-2xl bg-slate-950 flex flex-col items-center justify-center overflow-hidden shadow-inner border border-slate-800">
      {/* Soft loading placeholder */}
      {!loaded && !hasError && (
        <div className="absolute inset-0 bg-slate-900 animate-pulse flex items-center justify-center">
          <div className="w-5 h-5 border-2 border-slate-700 border-t-blue-500 rounded-full animate-spin" />
        </div>
      )}

      {/* Frame thumbnail from /thumbnail/{video_id}?t=<middle of clip> */}
      {!hasError ? (
        <img
          src={thumbnailUrl}
          alt={clip.title}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setHasError(true)}
          className={`w-full h-full object-contain transition-opacity duration-300 ${
            loaded ? 'opacity-100' : 'opacity-0'
          }`}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-slate-900 text-slate-500 text-[11px] font-semibold">
          Preview
        </div>
      )}

      {/* Play/Pause Button */}
      <button
        type="button"
        onClick={onPlayClick}
        aria-label={isCurrentlyPlaying ? 'Pause' : 'Play preview'}
        className="absolute w-10 h-10 rounded-full bg-blue-600/90 hover:bg-blue-600 text-white flex items-center justify-center shadow-lg transition-transform active:scale-95 cursor-pointer z-10 backdrop-blur-xs"
      >
        {isCurrentlyPlaying ? (
          <Pause className="w-4 h-4 fill-current" />
        ) : (
          <Play className="w-4 h-4 ml-0.5 fill-current" />
        )}
      </button>

      {/* Duration Badge */}
      <span className="absolute bottom-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-black/80 text-slate-200 tracking-wider z-10">
        {Math.max(1, Math.round(clip.end - clip.start))}s
      </span>
    </div>
  );
};

export const ScreenPick: React.FC<ScreenPickProps> = ({
  videoId,
  videoUrl,
  clips,
  setClips,
  selectedClip,
  onSelectClip,
  onNext,
  fancyOptions,
  setFancyOptions,
}) => {
  // Inputs above the list
  const [promptText, setPromptText] = useState('');
  const [lengthMode, setLengthMode] = useState<LengthMode>('30to60');
  const [customMinSec, setCustomMinSec] = useState<number>(15);
  const [customMaxSec, setCustomMaxSec] = useState<number>(60);

  // Loading and error states
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Preview video player state
  const [previewingClip, setPreviewingClip] = useState<Clip | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // "Make it fancy" toggle
  const [showFancy, setShowFancy] = useState(false);

  // Helper: compute min and max seconds
  const getMinMaxSeconds = (): { min: number; max: number } => {
    if (lengthMode === 'under30') return { min: 15, max: 30 };
    if (lengthMode === '30to60') return { min: 30, max: 60 };
    return {
      min: Math.max(5, customMinSec || 15),
      max: Math.max(customMinSec || 15, customMaxSec || 60),
    };
  };

  // Fetch highlights from API
  const loadHighlights = async () => {
    if (!videoId) {
      setErrorMessage('Please import or upload a video first.');
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    const { min, max } = getMinMaxSeconds();
    const promptVal = promptText.trim();

    console.log('[ScreenPick] Finding clips...', {
      video_id: videoId,
      prompt: promptVal || undefined,
      min_sec: min,
      max_sec: max,
    });

    try {
      const res = await fetchHighlights({
        video_id: videoId,
        prompt: promptVal || undefined,
        min_sec: min,
        max_sec: max,
      });

      console.log('[ScreenPick] Highlights response:', res);

      // Sort by total score, highest first
      const sorted = [...(res.clips || [])].sort(
        (a, b) => b.scores.total - a.scores.total
      );

      setClips(sorted);
      if (sorted.length > 0) {
        onSelectClip(sorted[0]);
      }
      setIsLoading(false);
    } catch (err: any) {
      console.error('[ScreenPick] Highlights error:', err);
      setIsLoading(false);
      setErrorMessage(
        err.message || 'The AI is busy right now. Please try again in a minute.'
      );
    }
  };

  // Auto-fetch highlights once on mount if clips is empty
  useEffect(() => {
    if (clips.length === 0) {
      loadHighlights();
    } else if (!selectedClip && clips.length > 0) {
      onSelectClip(clips[0]);
    }
  }, []);

  // Format duration into "0:42 long"
  const formatDuration = (start: number, end: number) => {
    const totalSecs = Math.max(0, Math.round(end - start));
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins}:${secs.toString().padStart(2, '0')} long`;
  };

  // Round Hook score badge color
  const getScoreBadgeClasses = (score: number) => {
    if (score >= 70) {
      return {
        bg: 'bg-emerald-500 text-white',
        text: 'text-emerald-700',
      };
    }
    if (score >= 40) {
      return {
        bg: 'bg-amber-500 text-white',
        text: 'text-amber-700',
      };
    }
    return {
      bg: 'bg-rose-500 text-white',
      text: 'text-rose-700',
    };
  };

  // Play clip preview strictly between start and end
  const handlePlayClip = (e: React.MouseEvent, clip: Clip) => {
    e.stopPropagation();
    onSelectClip(clip);

    if (previewingClip?.id === clip.id && isPlaying) {
      // Pause
      videoRef.current?.pause();
      setIsPlaying(false);
      return;
    }

    setPreviewingClip(clip);
    setIsPlaying(true);

    if (videoRef.current) {
      videoRef.current.currentTime = clip.start;
      videoRef.current.play().catch(() => {});
    }
  };

  // Keep playback within [clip.start, clip.end]
  const handleTimeUpdate = () => {
    if (videoRef.current && previewingClip) {
      if (videoRef.current.currentTime >= previewingClip.end) {
        videoRef.current.pause();
        videoRef.current.currentTime = previewingClip.start;
        setIsPlaying(false);
      }
    }
  };

  // Sort clips by total score descending
  const sortedClips = [...clips].sort((a, b) => b.scores.total - a.scores.total);

  return (
    <div className="flex flex-col flex-1 w-full max-w-md mx-auto px-4 py-4 pb-12">
      {/* Header */}
      <div className="mb-4 text-center">
        <h2 className="text-2xl font-black text-slate-800">Pick your favorite clip</h2>
        <p className="text-sm font-medium text-slate-500 mt-0.5">
          AI found the highest-scoring moments
        </p>
      </div>

      {/* Inputs above the list */}
      <div className="bg-white border-2 border-slate-200 rounded-3xl p-4 mb-5 shadow-sm flex flex-col gap-3">
        {/* Topic Search Box */}
        <div>
          <label className="text-xs font-bold text-slate-600 block mb-1.5">
            Want something specific? Type it here
          </label>
          <div className="relative flex items-center">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 pointer-events-none" />
            <input
              type="text"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              placeholder="e.g. funny joke, key advice, pricing..."
              className="w-full pl-10 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-2xl text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-600 font-medium transition-colors"
            />
          </div>
        </div>

        {/* Length Choice Buttons */}
        <div>
          <label className="text-xs font-bold text-slate-600 block mb-1.5">
            Clip Length
          </label>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setLengthMode('under30')}
              className={`py-2 px-2 rounded-2xl text-xs font-bold border-2 transition-all cursor-pointer ${
                lengthMode === 'under30'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
              }`}
            >
              Under 30 sec
            </button>
            <button
              type="button"
              onClick={() => setLengthMode('30to60')}
              className={`py-2 px-2 rounded-2xl text-xs font-bold border-2 transition-all cursor-pointer ${
                lengthMode === '30to60'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
              }`}
            >
              30–60 sec
            </button>
            <button
              type="button"
              onClick={() => setLengthMode('custom')}
              className={`py-2 px-2 rounded-2xl text-xs font-bold border-2 transition-all cursor-pointer ${
                lengthMode === 'custom'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
              }`}
            >
              Custom
            </button>
          </div>
        </div>

        {/* Custom duration number boxes */}
        {lengthMode === 'custom' && (
          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="text-[11px] font-bold text-slate-500 block mb-1">
                Min Seconds
              </label>
              <input
                type="number"
                min={5}
                max={customMaxSec || 60}
                value={customMinSec}
                onChange={(e) => setCustomMinSec(Number(e.target.value))}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-semibold text-slate-800 focus:outline-none focus:border-blue-600"
              />
            </div>
            <div>
              <label className="text-[11px] font-bold text-slate-500 block mb-1">
                Max Seconds
              </label>
              <input
                type="number"
                min={customMinSec || 15}
                max={180}
                value={customMaxSec}
                onChange={(e) => setCustomMaxSec(Number(e.target.value))}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-semibold text-slate-800 focus:outline-none focus:border-blue-600"
              />
            </div>
          </div>
        )}

        {/* Find/Refresh Clips Button */}
        <button
          type="button"
          onClick={loadHighlights}
          disabled={isLoading}
          className={`w-full py-2.5 px-4 rounded-2xl font-bold text-sm shadow-sm flex items-center justify-center gap-2 transition-all mt-1 ${
            isLoading
              ? 'bg-blue-400 text-white cursor-not-allowed opacity-80'
              : 'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer active:scale-[0.99]'
          }`}
        >
          <Sparkles className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Finding the best parts... (up to 1 minute)' : 'Find clips'}</span>
        </button>
      </div>

      {/* Hidden / Shared Video Player for precise previewing */}
      {videoUrl && (
        <video
          ref={videoRef}
          src={videoUrl}
          playsInline
          onError={() => {
            console.warn('Preview video failed to load.');
          }}
          onTimeUpdate={handleTimeUpdate}
          className="hidden"
        />
      )}

      {/* Active Preview Playing Banner */}
      {previewingClip && isPlaying && (
        <div className="mb-4 p-3 bg-blue-600 text-white rounded-2xl flex items-center justify-between shadow-md animate-in fade-in">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-white animate-ping" />
            <div>
              <p className="text-xs font-bold line-clamp-1">
                Playing: {previewingClip.title}
              </p>
              <p className="text-[11px] text-blue-100">
                Range: {previewingClip.start}s – {previewingClip.end}s
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={(e) => handlePlayClip(e, previewingClip)}
            className="px-2.5 py-1 bg-white/20 hover:bg-white/30 rounded-xl text-xs font-bold cursor-pointer"
          >
            Pause
          </button>
        </div>
      )}

      {/* Error state banner */}
      {errorMessage && (
        <div className="w-full mb-5 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start gap-3 animate-in fade-in">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm">
            <p className="font-bold text-rose-900 mb-0.5">Error</p>
            <p className="text-rose-700 font-medium whitespace-pre-wrap break-words">{errorMessage}</p>
            <button
              type="button"
              onClick={loadHighlights}
              className="mt-3 px-3.5 py-1.5 bg-rose-200/80 hover:bg-rose-200 text-rose-900 font-bold rounded-xl text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Try again</span>
            </button>
          </div>
        </div>
      )}

      {/* Loading state: "Finding the best parts... (up to 1 minute)" */}
      {isLoading && (
        <div className="w-full bg-white rounded-3xl border-2 border-slate-200 p-8 flex flex-col items-center justify-center text-center shadow-sm my-4 animate-in fade-in">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
            <Sparkles className="w-8 h-8 animate-spin text-blue-600" />
          </div>
          <h3 className="text-xl font-bold text-slate-800 mb-1">
            Finding the best parts... (up to 1 minute)
          </h3>
          <p className="text-sm font-medium text-slate-400">
            Gemini is scoring hooks, pacing, and viral potential
          </p>
        </div>
      )}

      {/* List of Clips */}
      {!isLoading && (
        <div className="flex flex-col gap-3.5 mb-6">
          {sortedClips.map((clip) => {
            const isSelected = selectedClip?.id === clip.id;
            const isCurrentlyPlaying =
              previewingClip?.id === clip.id && isPlaying;
            const scoreBadge = getScoreBadgeClasses(clip.scores.hook);

            return (
              <div
                key={clip.id}
                onClick={() => onSelectClip(clip)}
                className={`p-4 rounded-3xl border-2 transition-all cursor-pointer bg-white relative ${
                  isSelected
                    ? 'border-blue-600 shadow-md shadow-blue-500/10'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex gap-4 items-start">
                  {/* Thumbnail from /thumbnail/{video_id}?t=<middle of clip> */}
                  <ClipThumbnail
                    videoId={videoId || ''}
                    clip={clip}
                    isCurrentlyPlaying={isCurrentlyPlaying}
                    onPlayClick={(e) => handlePlayClip(e, clip)}
                  />

                  {/* Info */}
                  <div className="flex-1 flex flex-col justify-between min-w-0 min-h-28 py-0.5">
                    <div>
                      <h3 className="text-base font-bold text-slate-900 leading-snug line-clamp-2">
                        {clip.title}
                      </h3>
                      <p className="text-xs font-semibold text-slate-400 mt-0.5">
                        {formatDuration(clip.start, clip.end)}
                      </p>
                      {/* One short line with the reason */}
                      <p className="text-xs text-slate-600 line-clamp-2 mt-1 italic">
                        "{clip.reason}"
                      </p>
                    </div>

                    {/* Round score badge labelled "Hook Score" */}
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-black shadow-sm ${scoreBadge.bg}`}
                        >
                          {clip.scores.hook}
                        </span>
                        <div className="flex flex-col">
                          <span className="text-[11px] font-bold text-slate-700 leading-none">
                            Hook Score
                          </span>
                          <span className="text-[10px] font-medium text-slate-400 leading-none mt-0.5">
                            Total: {clip.scores.total}/100
                          </span>
                        </div>
                      </div>

                      {/* Selected Indicator */}
                      {isSelected && (
                        <span className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center">
                          <Check className="w-3.5 h-3.5 stroke-[3]" />
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {sortedClips.length === 0 && !errorMessage && (
            <div className="w-full bg-white rounded-3xl border-2 border-slate-200 p-8 flex flex-col items-center justify-center text-center shadow-sm my-4 animate-in fade-in">
              <p className="text-base font-bold text-slate-700">
                I couldn't find good clips. Try a different length or topic.
              </p>
            </div>
          )}
        </div>
      )}

      {/* "Make it fancy" Toggle */}
      <div className="bg-slate-50 border border-slate-200 rounded-3xl p-4 mb-6">
        <button
          type="button"
          onClick={() => setShowFancy(!showFancy)}
          className="w-full flex items-center justify-between text-left cursor-pointer group"
        >
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <span className="text-base font-bold text-slate-800 block">
                Make it fancy
              </span>
              <span className="text-xs text-slate-400 font-medium">
                Extra polish options
              </span>
            </div>
          </div>
          <SlidersHorizontal
            className={`w-5 h-5 text-slate-400 transition-transform ${
              showFancy ? 'rotate-90 text-blue-600' : ''
            }`}
          />
        </button>

        {showFancy && (
          <div className="mt-4 pt-4 border-t border-slate-200/80 flex flex-col gap-4">
            {/* Real Captions Switch */}
            <div className="flex items-center justify-between py-1">
              <div>
                <span className="text-sm font-bold text-slate-800 block">
                  Captions
                </span>
                <span className="text-xs text-slate-400 font-medium">
                  Dynamic animated word-by-word subtitles
                </span>
              </div>
              <input
                type="checkbox"
                checked={
                  fancyOptions.captions !== 'none' &&
                  fancyOptions.captions !== false
                }
                onChange={(e) => {
                  if (e.target.checked) {
                    setFancyOptions({
                      ...fancyOptions,
                      captions: 'bold_pop',
                    });
                  } else {
                    setFancyOptions({
                      ...fancyOptions,
                      captions: 'none',
                    });
                  }
                }}
                className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
              />
            </div>

            {/* 3 Big Style Tiles with Previews when Captions switch is ON */}
            {fancyOptions.captions !== 'none' && fancyOptions.captions !== false && (
              <div className="flex flex-col gap-2 pt-1 animate-in fade-in duration-200">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Select Caption Style
                </span>
                <div className="grid grid-cols-3 gap-2.5">
                  {/* Tile 1: Bold Pop */}
                  <div
                    onClick={() =>
                      setFancyOptions({
                        ...fancyOptions,
                        captions: 'bold_pop',
                      })
                    }
                    className={`p-2.5 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                      fancyOptions.captions === 'bold_pop' ||
                      fancyOptions.captions === true
                        ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="h-16 rounded-xl bg-slate-950 flex items-center justify-center p-1.5 mb-2 shadow-inner">
                      <p className="text-[12px] font-black uppercase text-white tracking-wider text-center leading-tight">
                        MAKE IT{' '}
                        <span className="text-yellow-400 font-black scale-110 inline-block drop-shadow">
                          POP
                        </span>
                      </p>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900 truncate">
                          Bold Pop
                        </p>
                        <p className="text-[10px] text-slate-400 font-medium">
                          Yellow pop
                        </p>
                      </div>
                      {(fancyOptions.captions === 'bold_pop' ||
                        fancyOptions.captions === true) && (
                        <span className="w-4 h-4 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 ml-1">
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Tile 2: Karaoke */}
                  <div
                    onClick={() =>
                      setFancyOptions({
                        ...fancyOptions,
                        captions: 'karaoke',
                      })
                    }
                    className={`p-2.5 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                      fancyOptions.captions === 'karaoke'
                        ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="h-16 rounded-xl bg-slate-950 flex items-center justify-center p-1.5 mb-2 shadow-inner">
                      <p className="text-[11px] font-semibold text-white/80 text-center leading-snug">
                        Watch{' '}
                        <span className="text-sky-400 font-bold bg-sky-500/25 px-1 rounded">
                          every
                        </span>{' '}
                        word
                      </p>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900 truncate">
                          Karaoke
                        </p>
                        <p className="text-[10px] text-slate-400 font-medium">
                          Blue highlight
                        </p>
                      </div>
                      {fancyOptions.captions === 'karaoke' && (
                        <span className="w-4 h-4 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 ml-1">
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Tile 3: Clean */}
                  <div
                    onClick={() =>
                      setFancyOptions({
                        ...fancyOptions,
                        captions: 'clean',
                      })
                    }
                    className={`p-2.5 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                      fancyOptions.captions === 'clean'
                        ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="h-16 rounded-xl bg-slate-950 flex items-end justify-center pb-2 px-1 mb-2 shadow-inner">
                      <p className="text-[10px] font-medium text-slate-100 text-center tracking-normal">
                        Clean subtitles
                      </p>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900 truncate">
                          Clean
                        </p>
                        <p className="text-[10px] text-slate-400 font-medium">
                          Minimal white
                        </p>
                      </div>
                      {fancyOptions.captions === 'clean' && (
                        <span className="w-4 h-4 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 ml-1">
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Single Compact List of Switches */}
            <div className="flex flex-col divide-y divide-slate-100">
              {/* Follow the speaker */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <Video className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Follow the speaker
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Auto-pans to face (takes a bit longer)
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.smart_reframe !== false}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      smart_reframe: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>

              {/* Remove silence */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <Scissors className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Remove silence
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Cut dead air
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.removeSilence}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      removeSilence: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>

              {/* Remove "um/uh" */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <MessageSquareOff className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Remove "um/uh"
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Eliminate filler words
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.remove_fillers ?? false}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      remove_fillers: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>

              {/* Music */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <Music className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Music
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Add background soundtrack
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.music}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      music: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>

              {/* Sound effects */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <Volume2 className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Sound effects
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Pops and whooshes
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.sfx ?? false}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      sfx: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>

              {/* Add pictures (B-roll) */}
              <label className="flex items-center justify-between cursor-pointer py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                    <Film className="w-4 h-4 text-slate-600" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-slate-800 block leading-tight">
                      Add pictures (B-roll)
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium block">
                      Relevant stock footage
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={fancyOptions.broll ?? false}
                  onChange={(e) =>
                    setFancyOptions({
                      ...fancyOptions,
                      broll: e.target.checked,
                    })
                  }
                  className="w-5 h-5 accent-blue-600 rounded cursor-pointer"
                />
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Next button */}
      <button
        type="button"
        onClick={onNext}
        disabled={!selectedClip}
        className={`w-full py-4 px-6 text-white text-lg font-bold rounded-2xl shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer ${
          selectedClip
            ? 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/25 active:scale-[0.99]'
            : 'bg-slate-300 shadow-none cursor-not-allowed'
        }`}
      >
        <span>Next</span>
      </button>
    </div>
  );
};
