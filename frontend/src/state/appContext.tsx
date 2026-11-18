/**
 * Single application store (ARCHITECTURE.md section 12).
 *
 * The action set below is the contract for every component task: components
 * never own state, they dispatch these actions. Extend it only through the
 * shared-file protocol (section 14.4).
 */

import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type {
  ErrorInfo,
  GenerationDetail,
  GenerationError,
  GenerationStatusValue,
  GenerationSummary,
  Voice,
} from "../types/contracts";

export interface CurrentGeneration {
  id: string;
  status: GenerationStatusValue;
  sentenceIndex: number;
  sentenceCount: number;
  detail?: GenerationDetail;
  audioUrl?: string;
}

export interface HistoryState {
  items: GenerationSummary[];
  total: number;
}

export interface AppState {
  inputText: string;
  sourceFilename: string | null;
  voices: Voice[];
  selectedVoiceId: string | null;
  rate: number;
  volume: number;
  current: CurrentGeneration | null;
  history: HistoryState;
  error: ErrorInfo | null;
}

export type AppAction =
  | { type: "SET_INPUT"; text: string }
  | { type: "SET_SOURCE_FILE"; filename: string | null }
  | { type: "VOICES_LOADED"; voices: Voice[] }
  | { type: "SET_VOICE"; voiceId: string }
  | { type: "SET_RATE"; rate: number }
  | { type: "SET_VOLUME"; volume: number }
  | { type: "GENERATION_CREATED"; id: string; status: GenerationStatusValue }
  | {
      type: "GENERATION_PROGRESS";
      id: string;
      status: GenerationStatusValue;
      sentenceIndex: number;
      sentenceCount: number;
    }
  | {
      type: "GENERATION_SUCCEEDED";
      id: string;
      detail: GenerationDetail;
      audioUrl?: string;
    }
  | { type: "GENERATION_FAILED"; id: string; error: GenerationError }
  | { type: "GENERATION_CANCELLED"; id: string }
  | { type: "SELECT_HISTORY_ITEM"; detail: GenerationDetail; audioUrl?: string }
  | { type: "HISTORY_LOADED"; items: GenerationSummary[]; total: number }
  | { type: "HISTORY_DELETED"; id: string }
  | { type: "SET_ERROR"; error: ErrorInfo }
  | { type: "CLEAR_ERROR" };

export const initialState: AppState = {
  inputText: "",
  sourceFilename: null,
  voices: [],
  selectedVoiceId: null,
  rate: 1,
  volume: 1,
  current: null,
  history: { items: [], total: 0 },
  error: null,
};

function errorInfo(error: GenerationError): ErrorInfo {
  return { code: error.code, message: error.message, details: null };
}

function currentFromDetail(
  detail: GenerationDetail,
  audioUrl: string | undefined,
): CurrentGeneration {
  return {
    id: detail.generationId,
    status: detail.status,
    sentenceIndex: 0,
    sentenceCount: 0,
    detail,
    audioUrl,
  };
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_INPUT":
      return { ...state, inputText: action.text, error: null };

    case "SET_SOURCE_FILE":
      return { ...state, sourceFilename: action.filename };

    case "VOICES_LOADED":
      return {
        ...state,
        voices: action.voices,
        selectedVoiceId:
          state.selectedVoiceId !== null &&
          action.voices.some((voice) => voice.id === state.selectedVoiceId)
            ? state.selectedVoiceId
            : (action.voices[0]?.id ?? null),
      };

    case "SET_VOICE":
      return { ...state, selectedVoiceId: action.voiceId };

    case "SET_RATE":
      return { ...state, rate: action.rate };

    case "SET_VOLUME":
      return { ...state, volume: action.volume };

    case "GENERATION_CREATED":
      return {
        ...state,
        error: null,
        current: {
          id: action.id,
          status: action.status,
          sentenceIndex: 0,
          sentenceCount: 0,
        },
      };

    case "GENERATION_PROGRESS":
      if (state.current === null || state.current.id !== action.id) {
        return state;
      }
      return {
        ...state,
        current: {
          ...state.current,
          status: action.status,
          sentenceIndex: action.sentenceIndex,
          sentenceCount: action.sentenceCount,
        },
      };

    case "GENERATION_SUCCEEDED":
      if (state.current === null || state.current.id !== action.id) {
        return state;
      }
      return {
        ...state,
        current: currentFromDetail(action.detail, action.audioUrl),
        error: null,
      };

    case "GENERATION_FAILED":
      if (state.current === null || state.current.id !== action.id) {
        return state;
      }
      return {
        ...state,
        current: { ...state.current, status: "failed" },
        error: errorInfo(action.error),
      };

    case "GENERATION_CANCELLED":
      if (state.current === null || state.current.id !== action.id) {
        return state;
      }
      return { ...state, current: { ...state.current, status: "cancelled" } };

    case "SELECT_HISTORY_ITEM":
      return {
        ...state,
        current: currentFromDetail(action.detail, action.audioUrl),
        error: null,
      };

    case "HISTORY_LOADED":
      return {
        ...state,
        history: { items: action.items, total: action.total },
      };

    case "HISTORY_DELETED": {
      const existed = state.history.items.some((item) => item.generationId === action.id);
      return {
        ...state,
        history: {
          items: existed
            ? state.history.items.filter((item) => item.generationId !== action.id)
            : state.history.items,
          total: existed ? Math.max(0, state.history.total - 1) : state.history.total,
        },
        current: state.current?.id === action.id ? null : state.current,
      };
    }

    case "SET_ERROR":
      return { ...state, error: action.error };

    case "CLEAR_ERROR":
      return { ...state, error: null };
  }
}

export interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const value = useMemo<AppContextValue>(() => ({ state, dispatch }), [state]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (value === null) {
    throw new Error("useApp must be used inside <AppProvider>.");
  }
  return value;
}
