import { API_BASE_URL } from '../config';
import { Clip, AspectRatio, WordTiming } from '../types';

export interface ImportResponse {
  video_id: string;
  duration: number;
  title: string;
}

export interface TranscribeResponse {
  words: WordTiming[];
}

export interface TranscribeStatusResponse {
  progress: number;
}

export interface HighlightsResponse {
  clips: Clip[];
}

export interface ExportResponse {
  file_url: string;
  duration?: number;
  credits?: string[];
}

/**
 * Helper to handle fetch responses and extract human-friendly error messages.
 */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = 'Something went wrong. Please try again.';
    try {
      const data = await res.json();
      if (data && data.detail) {
        if (typeof data.detail === 'string') {
          errorMsg = data.detail;
        } else if (Array.isArray(data.detail) && data.detail[0]?.msg) {
          errorMsg = data.detail[0].msg;
        }
      }
    } catch {
      // Failed to parse JSON error, use status text
      errorMsg = res.statusText || errorMsg;
    }
    throw new Error(errorMsg);
  }
  return res.json() as Promise<T>;
}

/**
 * Upload a local video file (MP4/MOV).
 */
export async function uploadVideoFile(file: File): Promise<ImportResponse> {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE_URL}/import-file`, {
      method: 'POST',
      body: formData,
    });
    return await handleResponse<ImportResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

/**
 * Import a video from YouTube or a URL.
 */
export async function importVideoUrl(url: string): Promise<ImportResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/import-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    });
    return await handleResponse<ImportResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

/**
 * Get video playback stream URL from backend.
 * Uses purely relative URL with no hardcoded hosts or ports.
 */
export function getVideoStreamUrl(videoId: string): string {
  return `/video/${videoId}`;
}

/**
 * Get frame thumbnail URL extracted with FFmpeg at timestamp t.
 */
export function getVideoThumbnailUrl(videoId: string, timeSec: number): string {
  const cleanTime = Math.max(0, Math.round(timeSec * 10) / 10);
  return `/thumbnail/${videoId}?t=${cleanTime}`;
}

/**
 * Transcribe a video to get word-level timestamps.
 */
export async function transcribeVideo(videoId: string): Promise<TranscribeResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ video_id: videoId }),
    });
    return await handleResponse<TranscribeResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

/**
 * Poll transcription progress (0-100).
 */
export async function getTranscribeStatus(
  videoId: string
): Promise<TranscribeStatusResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/transcribe-status/${videoId}`);
    return await handleResponse<TranscribeStatusResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

export interface HighlightsParams {
  video_id: string;
  prompt?: string;
  min_sec: number;
  max_sec: number;
}

/**
 * Fetch AI highlights from Gemini backend.
 */
export async function fetchHighlights(
  params: HighlightsParams
): Promise<HighlightsResponse> {
  console.log('[POST /highlights Request]:', params);
  try {
    const res = await fetch(`${API_BASE_URL}/highlights`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    console.log('[POST /highlights Response Status]:', res.status, res.statusText);
    const data = await handleResponse<HighlightsResponse>(res);
    console.log('[POST /highlights Response Data]:', data);
    return data;
  } catch (err: any) {
    console.error('[POST /highlights Error]:', err.message || err);
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

export interface ExportParams {
  video_id: string;
  clip: Clip;
  format: AspectRatio;
  options?: Record<string, any>;
}

/**
 * Export clip to target aspect ratio using backend FFmpeg.
 */
export async function exportClip(params: ExportParams): Promise<ExportResponse> {
  try {
    const cleanOptions = {
      ...params.options,
      remove_silence: params.options?.remove_silence ?? params.options?.removeSilence ?? false,
      remove_fillers: params.options?.remove_fillers ?? false,
      music: params.options?.music ?? false,
      sfx: params.options?.sfx ?? false,
      broll: params.options?.broll ?? false,
      smart_reframe: params.options?.smart_reframe ?? true,
      captions: params.options?.captions ?? 'bold_pop',
    };

    const res = await fetch(`${API_BASE_URL}/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...params,
        options: cleanOptions,
      }),
    });
    return await handleResponse<ExportResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(
        'Could not connect to the server. Please check your network and try again.'
      );
    }
    throw err;
  }
}

export interface MetadataResponse {
  titles: string[];
  description: string;
  hashtags: string[];
}

export interface ThumbnailsResponse {
  images: string[];
}

/**
 * Fetch 3 viral titles, description with backlink, and hashtags from Gemini.
 */
export async function fetchMetadata(params: {
  video_id: string;
  clip: Clip;
  source_url?: string;
}): Promise<MetadataResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/metadata`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    return await handleResponse<MetadataResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Could not connect to the server. Please check your network and try again.');
    }
    throw err;
  }
}

/**
 * Fetch 3 sharp, face-scored 9:16 thumbnails with punchy text overlays.
 */
export async function fetchThumbnails(params: {
  video_id: string;
  clip: Clip;
}): Promise<ThumbnailsResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/thumbnails`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    return await handleResponse<ThumbnailsResponse>(res);
  } catch (err: any) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Could not connect to the server. Please check your network and try again.');
    }
    throw err;
  }
}

export interface DiagnosticsResponse {
  ffmpeg: {
    found: boolean;
    version: string | null;
  };
  ffprobe: {
    found: boolean;
    version: string | null;
  };
  yt_dlp: {
    found: boolean;
    version: string;
  };
  gemini_api_key_set: boolean;
  gemini_model: string;
  free_disk_space: {
    free_bytes?: number;
    free_gb?: number;
    total_gb?: number;
    used_gb?: number;
    percent_free?: number;
    display?: string;
    error?: string;
  };
  whisper_model: string;
}

/**
 * Fetch system diagnostics (FFmpeg, ffprobe, yt-dlp, Gemini key status, disk space, Whisper model).
 */
export async function fetchDiagnostics(): Promise<DiagnosticsResponse> {
  const res = await fetch(`/diagnostics`);
  return await handleResponse<DiagnosticsResponse>(res);
}

export interface TestReportEntry {
  timestamp: string;
  step: string;
  duration_sec: number;
  file_size_bytes?: number;
  file_size: string;
  result: 'ok' | 'error';
  details?: string;
}

export interface TestReportResponse {
  entries: TestReportEntry[];
  error?: string;
}

/**
 * Fetch last 20 logged test benchmarks from GET /test-report.
 */
export async function fetchTestReport(): Promise<TestReportResponse> {
  const res = await fetch('/test-report');
  return await handleResponse<TestReportResponse>(res);
}


