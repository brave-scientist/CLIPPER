import React, { useState, useRef, useEffect } from 'react';
import {
  Upload,
  Link as LinkIcon,
  Sparkles,
  AlertCircle,
  RotateCcw,
  CheckCircle2,
  Headphones,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  uploadVideoFile,
  importVideoUrl,
  getVideoStreamUrl,
  transcribeVideo,
  getTranscribeStatus,
} from '../services/api';
import { WordTiming } from '../types';

interface ScreenAddProps {
  onNext: () => void;
  videoId: string | null;
  setVideoId: (id: string | null) => void;
  videoDuration: number | null;
  setVideoDuration: (dur: number | null) => void;
  videoTitle?: string;
  setVideoTitle?: (title: string) => void;
  videoUrl: string;
  setVideoUrl: (url: string) => void;
  transcript: WordTiming[];
  setTranscript: (words: WordTiming[]) => void;
  sourceUrl?: string;
  setSourceUrl?: (url: string) => void;
}

export const ScreenAdd: React.FC<ScreenAddProps> = ({
  onNext,
  videoId,
  setVideoId,
  videoDuration,
  setVideoDuration,
  videoTitle,
  setVideoTitle,
  videoUrl,
  setVideoUrl,
  transcript,
  setTranscript,
  sourceUrl,
  setSourceUrl,
}) => {
  const [urlInput, setUrlInput] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(20);

  // Transcription state
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcribeProgress, setTranscribeProgress] = useState(0);

  // Transcript viewer toggle
  const [showWords, setShowWords] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [importedFileName, setImportedFileName] = useState<string>('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoPlayerRef = useRef<HTMLVideoElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Clear polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Format duration into mm:ss
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Jump video player to specific word timestamp
  const handleWordClick = (startSec: number) => {
    if (videoPlayerRef.current) {
      videoPlayerRef.current.currentTime = startSec;
      videoPlayerRef.current.play().catch(() => {});
    }
  };

  // Start transcription pipeline and poll /transcribe-status every 2 seconds
  const startTranscription = async (vidId: string) => {
    setIsTranscribing(true);
    setTranscribeProgress(10);

    // Stop any prior interval
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    // Poll /transcribe-status every 2 seconds
    pollIntervalRef.current = setInterval(async () => {
      try {
        const statusRes = await getTranscribeStatus(vidId);
        if (typeof statusRes.progress === 'number') {
          setTranscribeProgress((prev) => Math.max(prev, statusRes.progress));
        }
      } catch {
        // Continue polling smoothly
      }
    }, 2000);

    try {
      const transcribeRes = await transcribeVideo(vidId);
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      setTranscribeProgress(100);
      setTranscript(transcribeRes.words || []);
      setIsTranscribing(false);
    } catch (err: any) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      setIsTranscribing(false);
      setErrorMessage(
        err.message || 'Could not transcribe video. Please try again.'
      );
    }
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processSelectedFile(e.target.files[0]);
    }
  };

  // Upload file process
  const processSelectedFile = async (file: File) => {
    setErrorMessage(null);
    const fileNameLower = file.name.toLowerCase();
    const isSupported =
      fileNameLower.endsWith('.mp4') ||
      fileNameLower.endsWith('.mov') ||
      file.type === 'video/mp4' ||
      file.type === 'video/quicktime';

    if (!isSupported) {
      setErrorMessage('Please upload an MP4 or MOV video file.');
      return;
    }

    setIsImporting(true);
    setImportProgress(20);

    const progressInterval = setInterval(() => {
      setImportProgress((prev) => (prev < 90 ? prev + 15 : prev));
    }, 400);

    try {
      const result = await uploadVideoFile(file);
      clearInterval(progressInterval);
      setImportProgress(100);

      setVideoId(result.video_id);
      setVideoDuration(result.duration);
      if (setVideoTitle && result.title) {
        setVideoTitle(result.title);
      }
      setVideoUrl(getVideoStreamUrl(result.video_id));
      setImportedFileName(result.title || file.name);
      setIsImporting(false);

      // Automatically start transcription
      await startTranscription(result.video_id);
    } catch (err: any) {
      clearInterval(progressInterval);
      setIsImporting(false);
      setErrorMessage(
        err.message || 'Could not upload the video. Please check your connection and try again.'
      );
    }
  };

  // Import from URL process
  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = urlInput.trim();
    if (!trimmed) return;

    setErrorMessage(null);
    setIsImporting(true);
    setImportProgress(25);

    const progressInterval = setInterval(() => {
      setImportProgress((prev) => (prev < 85 ? prev + 12 : prev));
    }, 600);

    try {
      const result = await importVideoUrl(trimmed);
      clearInterval(progressInterval);
      setImportProgress(100);

      setVideoId(result.video_id);
      setVideoDuration(result.duration);
      if (setVideoTitle && result.title) {
        setVideoTitle(result.title);
      }
      setVideoUrl(getVideoStreamUrl(result.video_id));
      setImportedFileName(result.title || 'Imported from URL');
      if (setSourceUrl) {
        setSourceUrl(trimmed);
      }
      setIsImporting(false);

      // Automatically start transcription
      await startTranscription(result.video_id);
    } catch (err: any) {
      clearInterval(progressInterval);
      setIsImporting(false);
      setErrorMessage(
        err.message || 'Could not import the video. Please check the URL and try again.'
      );
    }
  };

  const handleReset = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setVideoId(null);
    setVideoDuration(null);
    setVideoUrl('');
    setTranscript([]);
    setUrlInput('');
    setImportedFileName('');
    setErrorMessage(null);
    setIsTranscribing(false);
    setIsImporting(false);
  };

  return (
    <div className="flex flex-col items-center justify-center flex-1 w-full max-w-md mx-auto px-4 py-6">
      {/* 1. Error state banner */}
      {errorMessage && (
        <div className="w-full mb-5 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start gap-3 animate-in fade-in duration-200">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm">
            <p className="font-bold text-rose-900">Oops, something went wrong</p>
            <p className="text-rose-700 mt-0.5">{errorMessage}</p>
            <button
              type="button"
              onClick={() => {
                setErrorMessage(null);
                if (videoId && (!transcript || transcript.length === 0)) {
                  startTranscription(videoId);
                }
              }}
              className="mt-2.5 px-3 py-1.5 bg-rose-200/80 hover:bg-rose-200 text-rose-900 font-bold rounded-xl text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Try again</span>
            </button>
          </div>
        </div>
      )}

      {/* 2. Loading State: Importing video */}
      {isImporting && (
        <div className="w-full bg-white rounded-3xl border-2 border-slate-200 p-8 flex flex-col items-center justify-center text-center shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 relative">
            <Sparkles className="w-8 h-8 animate-pulse" />
          </div>

          <h3 className="text-xl font-bold text-slate-800 mb-1">
            {importProgress < 45 ? 'Downloading...' : importProgress < 80 ? 'Preparing video...' : 'Extracting audio...'}
          </h3>
          <p className="text-sm font-medium text-slate-400 mb-6">
            Fetching video, remuxing & pre-extracting audio
          </p>

          <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
            <div
              className="bg-blue-600 h-full rounded-full transition-all duration-300 ease-out"
              style={{ width: `${importProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* 3. Loading State: Transcribing ("Listening to your video...") */}
      {!isImporting && isTranscribing && (
        <div className="w-full bg-white rounded-3xl border-2 border-slate-200 p-8 flex flex-col items-center justify-center text-center shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 relative">
            <Headphones className="w-8 h-8 animate-bounce text-blue-600" />
          </div>

          <h3 className="text-xl font-bold text-slate-800 mb-1">
            {transcribeProgress < 20 ? 'Preparing audio...' : 'Listening & converting speech...'}
          </h3>
          <p className="text-sm font-medium text-slate-400 mb-6">
            Faster-Whisper AI is finding every word timestamp
          </p>

          {/* Progress bar polling every 2s */}
          <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden mb-2">
            <div
              className="bg-blue-600 h-full rounded-full transition-all duration-500 ease-out"
              style={{ width: `${transcribeProgress}%` }}
            />
          </div>
          <span className="text-xs font-bold text-slate-500">
            {transcribeProgress}% completed
          </span>
        </div>
      )}

      {/* 4. Success State: Video Player + "See the words" + Next button */}
      {!isImporting && !isTranscribing && videoId && videoUrl && (
        <div className="w-full flex flex-col gap-4 animate-in fade-in duration-300">
          <div className="bg-white rounded-3xl border-2 border-slate-200 overflow-hidden shadow-sm p-4">
            {/* Player */}
            <div className="relative aspect-video rounded-2xl bg-black overflow-hidden flex items-center justify-center mb-3">
              <video
                ref={videoPlayerRef}
                src={videoUrl}
                controls
                playsInline
                onError={() => {
                  console.warn('Video failed to load.');
                }}
                onTimeUpdate={() => {
                  if (videoPlayerRef.current) {
                    setCurrentTime(videoPlayerRef.current.currentTime);
                  }
                }}
                className="w-full h-full object-contain"
              />
            </div>

            {/* Video metadata row */}
            <div className="flex items-center justify-between px-1">
              <div className="min-w-0 pr-3">
                <div className="flex items-center gap-1.5 text-emerald-600 font-bold text-xs mb-0.5">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>Video ready & transcribed</span>
                </div>
                <p className="text-sm font-bold text-slate-900 line-clamp-2">
                  {videoTitle || importedFileName || `Video ${videoId}`}
                </p>
              </div>

              {videoDuration && (
                <span className="text-xs font-bold bg-slate-100 text-slate-700 px-3 py-1.5 rounded-xl shrink-0">
                  Length: {formatDuration(videoDuration)} ({videoDuration}s)
                </span>
              )}
            </div>

            {/* "See the words" Collapsible Section */}
            <div className="mt-4 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowWords(!showWords)}
                className="w-full flex items-center justify-between py-2 text-sm font-bold text-slate-700 hover:text-blue-600 transition-colors cursor-pointer"
              >
                <span className="flex items-center gap-2">
                  <span>See the words</span>
                  <span className="text-xs font-normal text-slate-400">
                    ({transcript.length} words)
                  </span>
                </span>
                {showWords ? (
                  <ChevronUp className="w-4 h-4 text-slate-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                )}
              </button>

              {showWords && (
                <div className="mt-2 p-3 bg-slate-50 rounded-2xl border border-slate-200 max-h-48 overflow-y-auto">
                  {transcript.length > 0 ? (
                    <div className="flex flex-wrap gap-x-1.5 gap-y-1 text-sm leading-relaxed text-slate-700">
                      {transcript.map((item, idx) => {
                        const isSpeaking =
                          currentTime >= item.start && currentTime <= item.end;
                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => handleWordClick(item.start)}
                            title={`Jump to ${formatDuration(item.start)}`}
                            className={`rounded px-1 py-0.5 transition-colors cursor-pointer font-medium text-left ${
                              isSpeaking
                                ? 'bg-blue-600 text-white font-bold'
                                : 'hover:bg-blue-100 hover:text-blue-700'
                            }`}
                          >
                            {item.word}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 text-center py-2">
                      No spoken words detected in this video.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Action button to proceed to Screen 2 */}
          <button
            type="button"
            onClick={onNext}
            className="w-full py-4 px-6 bg-blue-600 hover:bg-blue-700 active:scale-[0.99] text-white text-lg font-bold rounded-2xl shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <Sparkles className="w-5 h-5" />
            <span>Find the best parts</span>
          </button>

          <button
            type="button"
            onClick={handleReset}
            className="w-full py-2.5 text-sm font-bold text-slate-500 hover:text-slate-700 text-center transition-colors cursor-pointer"
          >
            Choose a different video
          </button>
        </div>
      )}

      {/* 5. Default Add View (Drop box + Link input) */}
      {!isImporting && !isTranscribing && !videoId && (
        <>
          {/* Dashed Drop & Upload Box */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`w-full aspect-[4/3] rounded-3xl border-3 border-dashed flex flex-col items-center justify-center p-6 text-center cursor-pointer transition-all duration-200 bg-white ${
              isDragging
                ? 'border-blue-500 bg-blue-50/50 scale-[1.01]'
                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50/60'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp4,.mov,video/mp4,video/quicktime"
              className="hidden"
              onChange={handleFileInput}
            />

            <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 shadow-sm">
              <Upload className="w-8 h-8" />
            </div>

            <p className="text-xl font-bold text-slate-800 mb-2 leading-snug">
              Paste a link or drop a video
            </p>
            <p className="text-sm font-medium text-slate-400">
              Accepts MP4 and MOV files
            </p>
          </div>

          {/* Link Input Bar */}
          <form onSubmit={handleUrlSubmit} className="w-full mt-4 flex flex-col gap-3">
            <div className="relative flex items-center">
              <LinkIcon className="w-5 h-5 text-slate-400 absolute left-4 pointer-events-none" />
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                className="w-full pl-12 pr-4 py-3.5 bg-white border-2 border-slate-200 rounded-2xl text-base text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-600 font-medium transition-colors"
              />
            </div>

            {/* Submit Button for URL */}
            <button
              type="submit"
              disabled={!urlInput.trim()}
              className={`w-full py-4 px-6 text-white text-lg font-bold rounded-2xl shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer ${
                urlInput.trim()
                  ? 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/25 active:scale-[0.99]'
                  : 'bg-slate-300 shadow-none cursor-not-allowed'
              }`}
            >
              <Sparkles className="w-5 h-5" />
              <span>Find the best parts</span>
            </button>
          </form>
        </>
      )}
    </div>
  );
};
