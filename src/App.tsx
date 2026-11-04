import { useState, useEffect } from 'react';
import { Step, Clip, AspectRatio, FancyOptions, WordTiming } from './types';
import { StepBar } from './components/StepBar';
import { ScreenAdd } from './components/ScreenAdd';
import { ScreenPick } from './components/ScreenPick';
import { ScreenSave } from './components/ScreenSave';
import { TestReport } from './components/TestReport';
import { Video } from 'lucide-react';

export default function App() {
  // Hidden /#report benchmark tool
  const [isReportOpen, setIsReportOpen] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return window.location.hash === '#report';
    }
    return false;
  });

  useEffect(() => {
    const handleHash = () => {
      setIsReportOpen(window.location.hash === '#report');
    };
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

  // Navigation state: 'add' | 'pick' | 'save'
  const [currentStep, setCurrentStep] = useState<Step>('add');

  // Video state from backend
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);
  const [videoTitle, setVideoTitle] = useState<string>('');
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [sourceUrl, setSourceUrl] = useState<string>('');
  const [transcript, setTranscript] = useState<WordTiming[]>([]);

  // Clips state
  const [clips, setClips] = useState<Clip[]>([]);
  const [selectedClip, setSelectedClip] = useState<Clip | null>(null);

  // Export options
  const [selectedFormat, setSelectedFormat] = useState<AspectRatio>('9:16');
  const [fancyOptions, setFancyOptions] = useState<FancyOptions>({
    captions: 'bold_pop',
    removeSilence: false,
    remove_fillers: false,
    music: false,
    sfx: false,
    broll: false,
    smart_reframe: true,
  });

  // Flow handlers
  const handleNextFromAdd = () => {
    setCurrentStep('pick');
  };

  const handleNextFromPick = () => {
    setCurrentStep('save');
  };

  const handleReset = () => {
    setCurrentStep('add');
    setVideoId(null);
    setVideoDuration(null);
    setVideoTitle('');
    setVideoUrl('');
    setTranscript([]);
    setClips([]);
    setSelectedClip(null);
  };

  if (isReportOpen) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans selection:bg-blue-100 selection:text-blue-900">
        <TestReport
          onBack={() => {
            window.location.hash = '';
            setIsReportOpen(false);
          }}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans selection:bg-blue-100 selection:text-blue-900">
      {/* Header bar */}
      <header className="bg-white border-b border-slate-200/80 sticky top-0 z-30">
        <div className="max-w-md mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-sm">
              <Video className="w-4 h-4" />
            </div>
            <span className="font-black text-lg tracking-tight text-slate-900">
              ClipSnap
            </span>
          </div>

          <span className="text-xs font-bold text-blue-600 bg-blue-50 border border-blue-200/60 px-2.5 py-1 rounded-full">
            Fast Clipper
          </span>
        </div>

        {/* Step Progress Bar */}
        <StepBar currentStep={currentStep} onSelectStep={setCurrentStep} />
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col items-center justify-start max-w-md w-full mx-auto">
        {currentStep === 'add' && (
          <ScreenAdd
            onNext={handleNextFromAdd}
            videoId={videoId}
            setVideoId={setVideoId}
            videoDuration={videoDuration}
            setVideoDuration={setVideoDuration}
            videoTitle={videoTitle}
            setVideoTitle={setVideoTitle}
            videoUrl={videoUrl}
            setVideoUrl={setVideoUrl}
            transcript={transcript}
            setTranscript={setTranscript}
            sourceUrl={sourceUrl}
            setSourceUrl={setSourceUrl}
          />
        )}

        {currentStep === 'pick' && (
          <ScreenPick
            videoId={videoId}
            videoDuration={videoDuration}
            videoTitle={videoTitle}
            videoUrl={videoUrl}
            clips={clips}
            setClips={setClips}
            selectedClip={selectedClip}
            onSelectClip={setSelectedClip}
            onNext={handleNextFromPick}
            fancyOptions={fancyOptions}
            setFancyOptions={setFancyOptions}
          />
        )}

        {currentStep === 'save' && (
          <ScreenSave
            videoId={videoId}
            selectedClip={selectedClip}
            selectedFormat={selectedFormat}
            setSelectedFormat={setSelectedFormat}
            fancyOptions={fancyOptions}
            setFancyOptions={setFancyOptions}
            sourceUrl={sourceUrl}
            onBackToPick={() => setCurrentStep('pick')}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  );
}
