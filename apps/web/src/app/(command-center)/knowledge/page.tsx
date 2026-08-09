"use client";

import { useEffect, useState, type FormEvent } from "react";

import { BookIcon, DatabaseIcon, SearchIcon } from "@/components/command-center/icons";
import { ragApi, type RagDocument, type RagSearchResult } from "@/lib/api";

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<RagSearchResult[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    ragApi
      .listDocuments()
      .then((res) => {
        if (!cancelled) setDocuments(res.documents ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load knowledge base.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await ragApi.search(trimmed);
      setResults(res.results ?? []);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed.");
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Knowledge</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Cybersecurity knowledge base and indexed documents</p>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the knowledge base…"
            className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] py-2.5 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-white/20 focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={!query.trim() || searching}
          className="inline-flex items-center justify-center rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </form>

      {searchError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {searchError}
        </div>
      ) : null}

      {results.length > 0 ? (
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-zinc-300">Search results</h2>
          {results.map((result) => (
            <div
              key={`${result.chunk_id}-${result.chunk_index}`}
              className="flex flex-col gap-1.5 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-medium text-zinc-400">{result.filename}</p>
                <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] font-medium text-zinc-400">
                  Page {result.page_number} · {Math.round(result.score * 100)}%
                </span>
              </div>
              <p className="text-sm text-zinc-300">{result.text}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-zinc-300">Indexed documents</h2>
        {loading ? (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] py-10 text-center text-sm text-zinc-500">
            Loading documents…
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-16">
            <DatabaseIcon className="mb-3 h-10 w-10 text-zinc-600" />
            <p className="text-sm font-medium text-zinc-400">No documents indexed</p>
            <p className="mt-1 text-xs text-zinc-600">Upload a PDF via the RAG API to populate the knowledge base.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex flex-col gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5"
              >
                <div className="flex items-center gap-2.5">
                  <BookIcon className="h-4.5 w-4.5 text-zinc-400" />
                  <p className="text-sm font-medium text-zinc-100">{doc.filename}</p>
                </div>
                <p className="text-xs text-zinc-500">
                  {doc.page_count} pages · {doc.total_chunks} chunks
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
