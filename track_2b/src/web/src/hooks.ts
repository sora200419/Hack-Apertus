// Data-fetching hooks: one-shot loads and the debounced what-if evaluation.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, isAbort } from "./api";
import type { EvaluateResponse, Product } from "./types";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Runs `load` on mount and on reload(); aborts the request on unmount. */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    loadRef
      .current(ctrl.signal)
      .then((d) => setData(d))
      .catch((err) => {
        if (!isAbort(err)) setError(errorMessage(err));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

export interface Evaluation {
  result: EvaluateResponse | null;
  /** The product object `result` was computed for. */
  evaluated: Product | null;
  loading: boolean;
  error: string | null;
}

const IDLE: Evaluation = { result: null, evaluated: null, loading: false, error: null };

/**
 * Re-evaluates `product` `delayMs` after the last edit; stale requests are aborted.
 * Changing `resetKey` (a newly loaded product) drops the previous result instead of showing it meanwhile.
 */
export function useDebouncedEvaluation(product: Product | null, resetKey: number, delayMs = 300): Evaluation {
  const [state, setState] = useState<Evaluation>(IDLE);

  useEffect(() => setState(IDLE), [resetKey]);

  useEffect(() => {
    if (!product) return;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    const timer = window.setTimeout(() => {
      api
        .evaluate(product, ctrl.signal)
        .then((result) => setState({ result, evaluated: product, loading: false, error: null }))
        .catch((err) => {
          if (!isAbort(err)) setState((s) => ({ ...s, loading: false, error: errorMessage(err) }));
        });
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [product, delayMs]);

  return state;
}
