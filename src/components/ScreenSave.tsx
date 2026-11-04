import React, { useState, useRef, useEffect } from 'react';
import { Clip, AspectRatio, FancyOptions } from '../types';
import {
  Download,
  Share2,
  CheckCircle2,
  RotateCcw,
  Sparkles,
  AlertCircle,
  Copy,
  Check,
  Loader2,
  Image as ImageIcon,
} from 'lucide-react';
import {
  exportClip,
  fetchMetadata,
  fetchThumbnails,
  MetadataResponse,
} from '../services/api';

interface ScreenSaveProps {
  videoId: string | null;
  selectedClip: Clip | null;
  selectedFormat: AspectRatio;
  setSelectedFormat: (format: AspectRatio) => void;
  fancyOptions: FancyOptions;
  setFancyOptions?: React.Dispatch<React.SetStateAction<FancyOptions>>;
  sourceUrl?: string;
  onBackToPick: () => void;
  onReset: () => void;
}

export const ScreenSave: React.FC<ScreenSaveProps> = ({
  videoId,
  selectedClip,
  selectedFormat,
  setSelectedFormat,
  fancyOptions,
  setFancyOptions,
  sourceUrl,
  onBackToPick,
  onReset,
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [isExported, setIsExported] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [exportedUrl, setExportedUrl] = useState<string>('');
  const [finalDuration, setFinalDuration] = useState<number | null>(null);
  const [credits, setCredits] = useState<string[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [copiedCombined, setCopiedCombined] = useState(false);

  // Metadata & Thumbnail states
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);
  const [selectedTitleIdx, setSelectedTitleIdx] = useState(0);
  const [copiedTitleIdx, setCopiedTitleIdx] = useState<number | null>(null);
  const [copiedDesc, setCopiedDesc] = useState(false);

  const [thumbnails, setThumbnails] = useState<string[]>([]);
  const [isLoadingThumbnails, setIsLoadingThumbnails] = useState(false);
  const [selectedThumbnailIdx, setSelectedThumbnailIdx] = useState(0);

  const videoPlayerRef = useRef<HTMLVideoElement>(null);

  // When export completes, fetch AI titles/description and thumbnail candidates
  useEffect(() => {
    if (isExported && videoId && selectedClip) {
      setIsLoadingMetadata(true);
      fetchMetadata({
        video_id: videoId,
        clip: selectedClip,
        source_url: sourceUrl || undefined,
      })
        .then((data) => setMetadata(data))
        .catch((err) => console.error('Failed to load metadata:', err))
        .finally(() => setIsLoadingMetadata(false));

      setIsLoadingThumbnails(true);
      fetchThumbnails({
        video_id: videoId,
        clip: selectedClip,
      })
        .then((data) => {
          if (data && data.images) {
            setThumbnails(data.images);
          }
        })
        .catch((err) => console.error('Failed to load thumbnails:', err))
        .finally(() => setIsLoadingThumbnails(false));
    }
  }, [isExported, videoId, selectedClip, sourceUrl]);

  // Visual pictorial size choices: Tall (9:16), Square (1:1), Wide (4:3)
  const formatOptions: {
    id: AspectRatio;
    name: string;
    ratio: string;
    subtext: string;
    renderPicture: (isSelected: boolean) => React.ReactNode;
  }[] = [
    {
      id: '9:16',
      name: 'Tall',
      ratio: '9:16',
      subtext: 'Reels / TikTok',
      renderPicture: (isSelected: boolean) => (
        <div
          className={`w-6 h-10 rounded-md border-2 transition-all flex items-center justify-center mb-1.5 ${
            isSelected
              ? 'border-blue-600 bg-blue-600/15 shadow-sm'
              : 'border-slate-400 bg-slate-100 group-hover:border-slate-500'
          }`}
        >
          <div
            className={`w-2.5 h-6 rounded-xs ${
              isSelected ? 'bg-blue-600' : 'bg-slate-300'
            }`}
          />
        </div>
      ),
    },
    {
      id: '1:1',
      name: 'Square',
      ratio: '1:1',
      subtext: 'Feed / Posts',
      renderPicture: (isSelected: boolean) => (
        <div
          className={`w-8 h-8 rounded-md border-2 transition-all flex items-center justify-center mb-1.5 ${
            isSelected
              ? 'border-blue-600 bg-blue-600/15 shadow-sm'
              : 'border-slate-400 bg-slate-100 group-hover:border-slate-500'
          }`}
        >
          <div
            className={`w-4.5 h-4.5 rounded-xs ${
              isSelected ? 'bg-blue-600' : 'bg-slate-300'
            }`}
          />
        </div>
      ),
    },
    {
      id: '4:3',
      name: 'Wide',
      ratio: '4:3',
      subtext: 'Standard Video',
      renderPicture: (isSelected: boolean) => (
        <div
          className={`w-10 h-7 rounded-md border-2 transition-all flex items-center justify-center mb-1.5 ${
            isSelected
              ? 'border-blue-600 bg-blue-600/15 shadow-sm'
              : 'border-slate-400 bg-slate-100 group-hover:border-slate-500'
          }`}
        >
          <div
            className={`w-6 h-3.5 rounded-xs ${
              isSelected ? 'bg-blue-600' : 'bg-slate-300'
            }`}
          />
        </div>
      ),
    },
  ];

  // Aspect ratio class for the video player container
  const getPlayerAspectRatioClass = () => {
    switch (selectedFormat) {
      case '9:16':
        return 'aspect-[9/16] max-h-[460px] max-w-[260px]';
      case '1:1':
        return 'aspect-square max-h-[340px] max-w-[340px]';
      case '4:3':
        return 'aspect-[4/3] max-h-[300px] max-w-[400px]';
    }
  };

  // Run real export
  const handleExport = async () => {
    if (!selectedClip) return;

    setIsExporting(true);
    setIsExported(false);
    setErrorMessage(null);
    setExportProgress(15);

    const progressTimer = setInterval(() => {
      setExportProgress((prev) => (prev < 90 ? prev + 15 : prev));
    }, 450);

    try {
      if (videoId) {
        const res = await exportClip({
          video_id: videoId,
          clip: selectedClip,
          format: selectedFormat,
          options: fancyOptions,
        });
        clearInterval(progressTimer);
        setExportProgress(100);
        setExportedUrl(res.file_url);
        if (res.duration) setFinalDuration(res.duration);
        if (res.credits) setCredits(res.credits);
        setIsExporting(false);
        setIsExported(true);
      } else {
        clearInterval(progressTimer);
        setIsExporting(false);
        setErrorMessage('No video loaded. Please import a video first.');
      }
    } catch (err: any) {
      clearInterval(progressTimer);
      setIsExporting(false);
      let msg = err.message || 'Could not export video. Please try again.';
      if (msg.includes('Command failed: ffmpeg') || msg.includes('ffmpeg version') || msg.includes('moov atom')) {
        msg = 'Encoding failed due to input format incompatibilities. Auto-repair is ready—click Try again.';
      }
      setErrorMessage(msg);
    }
  };

  // Download action
  const handleDownload = () => {
    if (!exportedUrl) return;
    const a = document.createElement('a');
    a.href = exportedUrl;
    a.download = `${selectedClip?.id || 'clip'}_${selectedFormat.replace(':', '_')}.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Web Share API with the video file, the chosen title and the description + hashtags
  const handleShare = async () => {
    if (!exportedUrl) return;

    setIsSharing(true);

    const chosenTitle =
      (metadata?.titles && metadata.titles[selectedTitleIdx]) ||
      selectedClip?.title ||
      'ClipSnap Video';

    const descText = metadata?.description || '';
    const tagsText = (metadata?.hashtags || []).join(' ');
    const combinedText = [descText, tagsText].filter(Boolean).join('\n\n');

    try {
      let file: File | null = null;
      try {
        const response = await fetch(exportedUrl);
        const blob = await response.blob();
        const filename = `${selectedClip?.id || 'clip'}_${selectedFormat.replace(':', '_')}.mp4`;
        file = new File([blob], filename, { type: 'video/mp4' });
      } catch (fileErr) {
        console.warn('Could not construct video File for sharing:', fileErr);
      }

      const shareData: ShareData = {
        title: chosenTitle,
        text: combinedText || chosenTitle,
      };

      if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
        shareData.files = [file];
      } else {
        shareData.url = exportedUrl;
      }

      if (navigator.share) {
        await navigator.share(shareData);
        setIsSharing(false);
        return;
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.warn('Share aborted or failed:', err);
      }
    } finally {
      setIsSharing(false);
    }

    // Fallback: Copy link or trigger download if share dialog was not available
    try {
      await navigator.clipboard.writeText(exportedUrl);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    } catch {
      handleDownload();
    }
  };

  // Helper to copy chosen title + description + hashtags together
  const handleCopyTitleAndDescription = async () => {
    const chosenTitle =
      (metadata?.titles && metadata.titles[selectedTitleIdx]) ||
      selectedClip?.title ||
      '';

    const descText = metadata?.description || '';
    const tagsText = (metadata?.hashtags || []).join(' ');
    const fullText = [chosenTitle, descText, tagsText].filter(Boolean).join('\n\n');

    await handleCopyText(fullText, () => {
      setCopiedCombined(true);
      setTimeout(() => setCopiedCombined(false), 2500);
    });
  };

  // Copy text helper
  const handleCopyText = async (text: string, onDone?: () => void) => {
    try {
      await navigator.clipboard.writeText(text);
      if (onDone) onDone();
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      if (onDone) onDone();
    }
  };

  // Download thumbnail helper
  const handleDownloadThumbnail = (url: string) => {
    if (!url) return;
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedClip?.id || 'clip'}_thumb.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="flex flex-col flex-1 w-full max-w-md mx-auto px-4 py-4 pb-12">
      {/* Header */}
      <div className="mb-4 text-center">
        <h2 className="text-2xl font-black text-slate-800">
          {isExported ? 'Your clip is ready!' : 'Export your clip'}
        </h2>
        <p className="text-sm font-medium text-slate-500 mt-0.5 line-clamp-1">
          {selectedClip ? selectedClip.title : 'Ready to render'}
        </p>
      </div>

      {/* Error state banner */}
      {errorMessage && (
        <div className="w-full mb-4 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start gap-3 animate-in fade-in">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm">
            <p className="font-bold text-rose-900">Export failed</p>
            <p className="text-rose-700 mt-0.5">{errorMessage}</p>
            <button
              type="button"
              onClick={handleExport}
              className="mt-2.5 px-3 py-1.5 bg-rose-200/80 hover:bg-rose-200 text-rose-900 font-bold rounded-xl text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Try again</span>
            </button>
          </div>
        </div>
      )}

      {/* 1. Pre-Export Screen: Picture buttons for aspect ratio */}
      {!isExported && !isExporting && (
        <>
          <div className="mb-6">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 text-center">
              Choose Clip Size
            </p>

            {/* Three size buttons with small pictures of tall, square, and wide rectangles */}
            <div className="grid grid-cols-3 gap-2.5">
              {formatOptions.map((opt) => {
                const isSelected = selectedFormat === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setSelectedFormat(opt.id)}
                    className={`group p-3 rounded-3xl border-2 flex flex-col items-center justify-center transition-all cursor-pointer ${
                      isSelected
                        ? 'border-blue-600 bg-blue-50/70 text-blue-700 shadow-sm scale-[1.02]'
                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                    }`}
                  >
                    {opt.renderPicture(isSelected)}
                    <span className="text-sm font-bold block">{opt.name}</span>
                    <span className="text-[11px] font-medium text-slate-400 block mt-0.5">
                      {opt.ratio}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Captions Style Selector & Switch on Screen 3 */}
          {setFancyOptions && (
            <div className="bg-white border-2 border-slate-200 rounded-3xl p-4 mb-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-bold text-slate-800 block">
                    Captions
                  </span>
                  <span className="text-xs text-slate-400 font-medium">
                    Burn animated word subtitles
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

              {fancyOptions.captions !== 'none' &&
                fancyOptions.captions !== false && (
                  <div className="mt-3 pt-3 border-t border-slate-100 flex flex-col gap-2 animate-in fade-in duration-200">
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      Caption Style
                    </span>
                    <div className="grid grid-cols-3 gap-2">
                      {/* Bold Pop */}
                      <div
                        onClick={() =>
                          setFancyOptions({
                            ...fancyOptions,
                            captions: 'bold_pop',
                          })
                        }
                        className={`p-2 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                          fancyOptions.captions === 'bold_pop' ||
                          fancyOptions.captions === true
                            ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                            : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                        }`}
                      >
                        <div className="h-12 rounded-xl bg-slate-950 flex items-center justify-center p-1 mb-1.5 shadow-inner">
                          <p className="text-[11px] font-black uppercase text-white tracking-wide text-center">
                            GO <span className="text-yellow-400">BIG</span>
                          </p>
                        </div>
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-slate-800">
                            Bold Pop
                          </p>
                          {(fancyOptions.captions === 'bold_pop' ||
                            fancyOptions.captions === true) && (
                            <span className="w-3.5 h-3.5 rounded-full bg-blue-600 text-white flex items-center justify-center">
                              <Check className="w-2 h-2 stroke-[3]" />
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Karaoke */}
                      <div
                        onClick={() =>
                          setFancyOptions({
                            ...fancyOptions,
                            captions: 'karaoke',
                          })
                        }
                        className={`p-2 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                          fancyOptions.captions === 'karaoke'
                            ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                            : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                        }`}
                      >
                        <div className="h-12 rounded-xl bg-slate-950 flex items-center justify-center p-1 mb-1.5 shadow-inner">
                          <p className="text-[10px] font-bold text-white text-center">
                            Word by <span className="text-sky-400">word</span>
                          </p>
                        </div>
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-slate-800">
                            Karaoke
                          </p>
                          {fancyOptions.captions === 'karaoke' && (
                            <span className="w-3.5 h-3.5 rounded-full bg-blue-600 text-white flex items-center justify-center">
                              <Check className="w-2 h-2 stroke-[3]" />
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Clean */}
                      <div
                        onClick={() =>
                          setFancyOptions({
                            ...fancyOptions,
                            captions: 'clean',
                          })
                        }
                        className={`p-2 rounded-2xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                          fancyOptions.captions === 'clean'
                            ? 'border-blue-600 bg-blue-50/70 shadow-sm'
                            : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                        }`}
                      >
                        <div className="h-12 rounded-xl bg-slate-950 flex items-end justify-center pb-1.5 px-1 mb-1.5 shadow-inner">
                          <p className="text-[9px] font-normal text-slate-200 text-center">
                            Clean text
                          </p>
                        </div>
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-slate-800">
                            Clean
                          </p>
                          {fancyOptions.captions === 'clean' && (
                            <span className="w-3.5 h-3.5 rounded-full bg-blue-600 text-white flex items-center justify-center">
                              <Check className="w-2 h-2 stroke-[3]" />
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              {/* Follow the speaker switch */}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
                <div>
                  <span className="text-sm font-bold text-slate-800 block">
                    Follow the speaker
                  </span>
                  <span className="text-[11px] text-slate-400 font-medium block">
                    Auto-pans camera to face (takes a bit longer)
                  </span>
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
              </div>
            </div>
          )}

          {/* Clip Summary Card */}
          {selectedClip && (
            <div className="bg-white border-2 border-slate-200 rounded-3xl p-4 mb-6 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                  Hook Score: {selectedClip.scores.hook}/100
                </span>
                <div className="flex items-center gap-1.5 flex-wrap justify-end">
                  {fancyOptions.smart_reframe !== false && (
                    <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-2 py-0.5 rounded-full">
                      Follow Speaker
                    </span>
                  )}
                  {fancyOptions.removeSilence && (
                    <span className="text-[11px] font-bold text-teal-700 bg-teal-50 border border-teal-200/60 px-2 py-0.5 rounded-full">
                      No Silence
                    </span>
                  )}
                  {fancyOptions.remove_fillers && (
                    <span className="text-[11px] font-bold text-cyan-700 bg-cyan-50 border border-cyan-200/60 px-2 py-0.5 rounded-full">
                      No Fillers
                    </span>
                  )}
                  {fancyOptions.broll && (
                    <span className="text-[11px] font-bold text-purple-700 bg-purple-50 border border-purple-200/60 px-2 py-0.5 rounded-full">
                      B-Roll
                    </span>
                  )}
                  {fancyOptions.music && (
                    <span className="text-[11px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200/60 px-2 py-0.5 rounded-full">
                      Music
                    </span>
                  )}
                  {fancyOptions.sfx && (
                    <span className="text-[11px] font-bold text-pink-700 bg-pink-50 border border-pink-200/60 px-2 py-0.5 rounded-full">
                      SFX
                    </span>
                  )}
                  {fancyOptions.captions && fancyOptions.captions !== 'none' && (
                    <span className="text-[11px] font-bold text-amber-700 bg-amber-50 border border-amber-200/60 px-2 py-0.5 rounded-full capitalize">
                      {fancyOptions.captions === true
                        ? 'Bold Pop'
                        : String(fancyOptions.captions).replace('_', ' ')}
                    </span>
                  )}
                  <span className="text-xs font-bold text-slate-500">
                    {Math.round(selectedClip.end - selectedClip.start)}s
                  </span>
                </div>
              </div>
              <h3 className="font-bold text-slate-800 text-sm leading-snug">
                {selectedClip.title}
              </h3>
              <p className="text-xs text-slate-500 italic mt-1 line-clamp-2">
                "{selectedClip.reason}"
              </p>
            </div>
          )}

          {/* Big Export Button */}
          <button
            type="button"
            onClick={handleExport}
            disabled={!selectedClip}
            className="w-full py-4 px-6 bg-blue-600 hover:bg-blue-700 active:scale-[0.99] text-white text-lg font-bold rounded-2xl shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <Sparkles className="w-5 h-5" />
            <span>Export</span>
          </button>
        </>
      )}

      {/* 2. Loading State: "Cutting clip..." / "Reframing active speaker..." */}
      {isExporting && (
        <div className="w-full bg-white rounded-3xl border-2 border-slate-200 p-8 flex flex-col items-center justify-center text-center shadow-sm my-auto">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
            <Sparkles className="w-8 h-8 animate-pulse text-blue-600" />
          </div>

          <h3 className="text-xl font-bold text-slate-800 mb-1">
            {exportProgress < 25
              ? 'Cutting clip...'
              : exportProgress < 50
              ? 'Reframing active speaker...'
              : exportProgress < 75
              ? 'Adding captions & polish...'
              : 'Rendering final video...'}
          </h3>
          <p className="text-sm font-medium text-slate-400 mb-6">
            {exportProgress < 50
              ? 'Trimming segment and tracking face movement'
              : 'Applying subtitles, audio overlays & fast encoding'}
          </p>

          <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden mb-2">
            <div
              className="bg-blue-600 h-full rounded-full transition-all duration-300 ease-out"
              style={{ width: `${exportProgress}%` }}
            />
          </div>
          <span className="text-xs font-bold text-slate-500">
            {exportProgress}% completed
          </span>
        </div>
      )}

      {/* 3. Exported Success View: Finished video in player + Download + Share + Make another */}
      {isExported && (
        <div className="flex flex-col items-center gap-4 animate-in fade-in duration-300 w-full">
          {/* Video Player showing finished video */}
          <div
            className={`w-full ${getPlayerAspectRatioClass()} mx-auto bg-black rounded-3xl overflow-hidden shadow-xl border-2 border-slate-200 flex items-center justify-center relative`}
          >
            <video
              ref={videoPlayerRef}
              src={exportedUrl}
              controls
              playsInline
              autoPlay
              className="w-full h-full object-contain"
            />
          </div>

          <div className="w-full flex items-center justify-between px-2 text-xs font-bold text-slate-600">
            <span className="flex items-center gap-1.5 text-emerald-600">
              <CheckCircle2 className="w-4 h-4" />
              <span>Exported ({selectedFormat})</span>
            </span>
            <span>
              {finalDuration != null
                ? `${finalDuration.toFixed(1)}s`
                : `${Math.round((selectedClip?.end || 0) - (selectedClip?.start || 0))}s`}{' '}
              MP4
            </span>
          </div>

          {/* Credits notice if B-roll was inserted */}
          {credits && credits.length > 0 && (
            <div className="w-full p-2.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-600 text-[11px] leading-relaxed">
              <span className="font-bold text-slate-700 block mb-0.5">
                Stock Media Credits:
              </span>
              <ul className="list-disc list-inside space-y-0.5 text-slate-500">
                {credits.map((c, idx) => (
                  <li key={idx} className="truncate">
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Copied Link Toast */}
          {copiedLink && (
            <div className="w-full p-2.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 animate-in fade-in">
              <Check className="w-4 h-4" />
              <span>Video link copied to clipboard!</span>
            </div>
          )}

          {/* Main Action: Share Button */}
          <button
            type="button"
            onClick={handleShare}
            disabled={isSharing}
            className="w-full py-4 px-6 bg-blue-600 hover:bg-blue-700 active:scale-[0.99] text-white text-lg font-bold rounded-2xl shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2.5 cursor-pointer transition-all disabled:opacity-75"
          >
            {isSharing ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Preparing share...</span>
              </>
            ) : (
              <>
                <Share2 className="w-5 h-5 stroke-[2.5]" />
                <span>Share</span>
              </>
            )}
          </button>

          {/* Fallback Buttons: Download video & Copy title & description */}
          <div className="grid grid-cols-2 gap-2.5 w-full">
            <button
              type="button"
              onClick={handleDownload}
              className="py-3 px-3.5 bg-slate-100 hover:bg-slate-200 active:scale-[0.99] text-slate-800 text-sm font-bold rounded-2xl flex items-center justify-center gap-2 cursor-pointer transition-all border border-slate-200/80"
            >
              <Download className="w-4 h-4 text-slate-600 shrink-0" />
              <span className="truncate">Download video</span>
            </button>

            <button
              type="button"
              onClick={handleCopyTitleAndDescription}
              className="py-3 px-3.5 bg-slate-100 hover:bg-slate-200 active:scale-[0.99] text-slate-800 text-sm font-bold rounded-2xl flex items-center justify-center gap-2 cursor-pointer transition-all border border-slate-200/80"
            >
              {copiedCombined ? (
                <>
                  <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span className="text-emerald-700 font-bold truncate">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4 text-slate-600 shrink-0" />
                  <span className="truncate">Copy title & desc</span>
                </>
              )}
            </button>
          </div>

          {/* Small tip under the buttons */}
          <p className="text-xs text-slate-400 text-center font-medium px-2 leading-relaxed">
            On your phone, choose YouTube, Instagram or TikTok from the share menu.
          </p>

          {/* Friendly Title & Thumbnail Section */}
          <div className="w-full bg-slate-50 border border-slate-200 rounded-3xl p-5 my-2 flex flex-col gap-5 text-left shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-200/80 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-blue-600" />
                  <span>Title & thumbnail</span>
                </h3>
                <p className="text-xs text-slate-400 font-medium mt-0.5">
                  Viral titles, caption description, and 9:16 covers
                </p>
              </div>
            </div>

            {/* 1. Three Title Choices as Tappable Cards */}
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Title Choices
                </span>
                <span className="text-[11px] text-slate-400 font-medium">
                  Max 60 characters
                </span>
              </div>

              {isLoadingMetadata ? (
                <div className="py-6 flex flex-col items-center justify-center text-slate-400 gap-2 bg-white rounded-2xl border border-slate-200/80">
                  <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                  <span className="text-xs font-semibold">Generating curiosity-driven titles...</span>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {(metadata?.titles || [selectedClip?.title || 'Must-watch clip']).map((title, idx) => {
                    const isSelected = selectedTitleIdx === idx;
                    const isCopied = copiedTitleIdx === idx;
                    return (
                      <div
                        key={idx}
                        onClick={() => setSelectedTitleIdx(idx)}
                        className={`p-3 rounded-2xl border-2 cursor-pointer transition-all flex items-center justify-between gap-3 ${
                          isSelected
                            ? 'border-blue-600 bg-blue-50/70 shadow-xs'
                            : 'border-slate-200 bg-white hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <span
                            className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                              isSelected ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500'
                            }`}
                          >
                            {idx + 1}
                          </span>
                          <span className="text-xs font-bold text-slate-800 line-clamp-2">
                            {title}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[10px] font-semibold text-slate-400">
                            {title.length}/60
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCopyText(title, () => {
                                setCopiedTitleIdx(idx);
                                setTimeout(() => setCopiedTitleIdx(null), 1800);
                              });
                            }}
                            className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer"
                            title="Copy title"
                          >
                            {isCopied ? (
                              <Check className="w-3.5 h-3.5 text-emerald-600" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 2. Description Text Box with Copy Button & Backlink */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Description & Backlink
                </span>
                <button
                  type="button"
                  onClick={() => {
                    const fullDesc = `${metadata?.description || ''}\n\n${(metadata?.hashtags || []).join(' ')}`.trim();
                    handleCopyText(fullDesc, () => {
                      setCopiedDesc(true);
                      setTimeout(() => setCopiedDesc(false), 1800);
                    });
                  }}
                  disabled={!metadata}
                  className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1 cursor-pointer disabled:opacity-50"
                >
                  {copiedDesc ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-600">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy Description</span>
                    </>
                  )}
                </button>
              </div>

              {isLoadingMetadata ? (
                <div className="h-20 bg-white border border-slate-200 rounded-2xl flex items-center justify-center">
                  <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                </div>
              ) : (
                <div className="bg-white border border-slate-200 rounded-2xl p-3.5 text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">
                  <p>{metadata?.description || `Watch this clip on ${selectedClip?.title}. Subscribe for more!`}</p>
                  {metadata?.hashtags && metadata.hashtags.length > 0 && (
                    <p className="mt-2 text-blue-600 font-semibold">
                      {metadata.hashtags.join(' ')}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* 3. Row of 3 Thumbnail Options */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Cover Thumbnails (9:16)
                </span>
                {thumbnails.length > 0 && (
                  <button
                    type="button"
                    onClick={() => handleDownloadThumbnail(thumbnails[selectedThumbnailIdx])}
                    className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1 cursor-pointer"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download Cover</span>
                  </button>
                )}
              </div>

              {isLoadingThumbnails ? (
                <div className="py-8 flex flex-col items-center justify-center text-slate-400 gap-2 bg-white rounded-2xl border border-slate-200">
                  <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
                  <span className="text-xs font-semibold">Selecting sharpest frames & drawing text hooks...</span>
                </div>
              ) : thumbnails.length > 0 ? (
                <div className="grid grid-cols-3 gap-2.5">
                  {thumbnails.map((thumbUrl, idx) => {
                    const isSelected = selectedThumbnailIdx === idx;
                    return (
                      <div
                        key={idx}
                        onClick={() => setSelectedThumbnailIdx(idx)}
                        className={`relative aspect-[9/16] rounded-2xl overflow-hidden cursor-pointer transition-all border-3 ${
                          isSelected
                            ? 'border-blue-600 shadow-md ring-2 ring-blue-600/30 scale-[1.02]'
                            : 'border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        <img
                          src={thumbUrl}
                          alt={`Cover ${idx + 1}`}
                          className="w-full h-full object-cover"
                        />
                        {isSelected && (
                          <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center shadow">
                            <Check className="w-3 h-3 stroke-[3]" />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-slate-400 bg-white rounded-2xl border border-slate-200">
                  Thumbnails are generated automatically after export.
                </div>
              )}
            </div>
          </div>

          {/* Make Another Button (goes back to screen 2 "Pick") */}
          <button
            type="button"
            onClick={onBackToPick}
            className="w-full py-3 px-4 text-blue-600 hover:text-blue-700 font-bold rounded-2xl flex items-center justify-center gap-2 text-sm transition-colors cursor-pointer mt-1"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Make another</span>
          </button>
        </div>
      )}
    </div>
  );
};
