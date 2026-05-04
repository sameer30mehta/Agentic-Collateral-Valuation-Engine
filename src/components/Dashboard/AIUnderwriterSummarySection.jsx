import React, { useState } from 'react';
import { API_BASE_URL } from '../../lib/api';

const SOURCE_LABEL = {
  ollama: 'Ollama',
  rule_based_fallback: 'Rule-based fallback',
  unavailable: 'Unavailable'
};

const SUMMARY_QUALITY_LABEL = {
  fast: 'Fast summary',
  enhanced: 'Enhanced summary',
  fallback: 'Rule-based fallback',
  unavailable: 'Unavailable'
};

function displayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not available';
  return value;
}

function displayModelValue(summaryResponse) {
  if (summaryResponse?.source === 'rule_based_fallback') return 'Rule-based fallback';
  return displayValue(summaryResponse?.modelUsed);
}

function StatusBadge({ children, tone = 'slate' }) {
  const toneClass = {
    slate: 'bg-slate-50 text-slate-600 border-slate-200',
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-100',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200'
  }[tone];

  return (
    <span className={`px-3 py-1.5 rounded-lg text-[11px] font-bold uppercase tracking-widest border ${toneClass}`}>
      {children}
    </span>
  );
}

function ListBlock({ title, items, tone = 'slate', emptyText = 'Not available' }) {
  const iconClass = tone === 'positive'
    ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
    : tone === 'risk'
      ? 'bg-red-50 text-red-600 border-red-100'
      : 'bg-indigo-50 text-indigo-600 border-indigo-100';

  return (
    <div className="bg-slate-50 rounded-xl border border-slate-200 p-4">
      <h4 className="text-sm font-bold text-slate-800 mb-3 border-b border-slate-200 pb-2">{title}</h4>
      <ul className="space-y-2">
        {(items?.length ? items : [emptyText]).map((item, index) => (
          <li key={`${title}-${index}`} className="flex items-start gap-2 text-[12px] font-semibold text-slate-600 leading-snug">
            <span className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${iconClass}`}>
              <span className="material-symbols-outlined text-[14px]">
                {tone === 'positive' ? 'check' : tone === 'risk' ? 'priority_high' : 'description'}
              </span>
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LoadingState() {
  return (
    <section className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between gap-4 mb-5">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-indigo-500">psychology</span>
          <h3 className="text-lg font-headline font-bold text-slate-800">AI Underwriter Summary</h3>
          <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] rounded font-mono border border-indigo-100">LLM_EXPLANATION</span>
        </div>
        <StatusBadge tone="indigo">Generating</StatusBadge>
      </div>
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-5 flex items-center gap-4">
        <div className="w-9 h-9 rounded-full border-4 border-indigo-100 border-t-indigo-600 animate-spin shrink-0"></div>
        <div>
          <p className="text-sm font-bold text-indigo-900">Generating fast AI summary</p>
          <p className="text-[12px] font-medium text-indigo-700 mt-1">Calling local Ollama with llama3.2:3b first and giving it up to 300 seconds before rule-based fallback handling.</p>
        </div>
      </div>
    </section>
  );
}

function DebugAttempts({ debug }) {
  if (!debug?.attempts?.length) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-3">LLM attempt trace</p>
      <div className="space-y-2">
        {debug.attempts.map((attempt, index) => (
          <div key={`${attempt.model}-${index}`} className="flex flex-col md:flex-row md:items-start gap-2 md:gap-4 text-[12px] font-semibold text-slate-600">
            <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest border w-max ${
              attempt.status === 'success'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-red-50 text-red-700 border-red-200'
            }`}>
              {attempt.status}
            </span>
            <span className="font-mono text-slate-800">{attempt.model}</span>
            {attempt.error && <span className="text-red-700 break-words">{attempt.error}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function EnhancementStatus({ enhancementState }) {
  if (!enhancementState?.status || enhancementState.status === 'idle') return null;

  const toneClass = enhancementState.status === 'upgraded'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
    : enhancementState.status === 'unavailable'
      ? 'border-amber-200 bg-amber-50 text-amber-800'
      : enhancementState.status === 'scheduled'
        ? 'border-sky-200 bg-sky-50 text-sky-800'
      : 'border-indigo-200 bg-indigo-50 text-indigo-800';

  const label = enhancementState.status === 'upgraded'
    ? 'Upgrade complete'
    : enhancementState.status === 'unavailable'
      ? 'Enhanced unavailable'
      : enhancementState.status === 'scheduled'
        ? 'Upgrade queued'
      : 'Enhancing';

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`}>
      <p className="text-[10px] font-bold uppercase tracking-wider mb-1">{label}</p>
      <p className="text-[12px] font-semibold leading-snug">{enhancementState.message}</p>
    </div>
  );
}

function DeveloperDiagnostics({ summaryResponse, enhancementState }) {
  const [open, setOpen] = useState(false);
  if (!import.meta.env.DEV) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-3 text-left text-[12px] font-bold text-slate-600"
      >
        <span>Developer diagnostics</span>
        <span className="material-symbols-outlined text-[18px]">{open ? 'expand_less' : 'expand_more'}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-1 gap-x-4 gap-y-1 rounded-lg bg-slate-50 p-3 font-mono text-[11px] text-slate-600 md:grid-cols-2">
            <span>apiBaseUrl: {API_BASE_URL}</span>
            <span>source: {displayValue(summaryResponse?.source)}</span>
            <span>modelUsed: {displayValue(summaryResponse?.modelUsed)}</span>
            <span>summaryQuality: {displayValue(summaryResponse?.summaryQuality)}</span>
            <span>fallbackUsed: {String(Boolean(summaryResponse?.fallbackUsed))}</span>
            <span>enhancementStatus: {displayValue(enhancementState?.status)}</span>
          </div>
          <DebugAttempts debug={summaryResponse?.llmDebug} />
        </div>
      )}
    </div>
  );
}

export default function AIUnderwriterSummarySection({ summaryResponse, isLoading, enhancementState }) {
  if (isLoading) return <LoadingState />;

  const source = summaryResponse?.source || 'unavailable';
  const summary = summaryResponse?.summary;
  const summaryQuality = summaryResponse?.summaryQuality || 'unavailable';

  return (
    <section className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="material-symbols-outlined text-indigo-500">psychology</span>
            <h3 className="text-lg font-headline font-bold text-slate-800">AI Underwriter Summary</h3>
            <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] rounded font-mono border border-indigo-100">LLM_EXPLANATION</span>
          </div>
          <p className="text-sm text-slate-500 font-medium">
            AI summary explains system outputs. Numeric values, scores, LTV, and flags are computed by deterministic engines.
          </p>
          {source === 'rule_based_fallback' && (
            <p className="mt-2 text-[12px] font-semibold text-amber-700">
              Rule-based summary shown because local LLM was unavailable or timed out.
            </p>
          )}
        </div>
        <div className="flex flex-wrap lg:justify-end gap-2">
          <StatusBadge tone={source === 'ollama' ? 'emerald' : source === 'rule_based_fallback' ? 'amber' : 'slate'}>
            Source: {SOURCE_LABEL[source] || SOURCE_LABEL.unavailable}
          </StatusBadge>
          <StatusBadge tone={summaryQuality === 'enhanced' ? 'emerald' : summaryQuality === 'fast' ? 'indigo' : summaryQuality === 'fallback' ? 'amber' : 'slate'}>
            Summary: {SUMMARY_QUALITY_LABEL[summaryQuality] || SUMMARY_QUALITY_LABEL.unavailable}
          </StatusBadge>
          <StatusBadge tone="slate">Model: {displayModelValue(summaryResponse)}</StatusBadge>
          {summaryResponse?.fallbackUsed && source === 'ollama' && <StatusBadge tone="amber">Fallback used</StatusBadge>}
        </div>
      </div>

      {!summary ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
          <p className="text-sm font-bold text-slate-800">AI underwriter summary unavailable</p>
          <p className="text-[12px] font-medium text-slate-600 mt-1">
            Deterministic valuation, verification, historical, and portfolio outputs remain available for review.
          </p>
          {summaryResponse?.error && (
            <p className="mt-3 text-[12px] font-bold text-red-700">
              {summaryResponse.error}
            </p>
          )}
          <div className="mt-4">
            <EnhancementStatus enhancementState={enhancementState} />
          </div>
          <div className="mt-4">
            <DeveloperDiagnostics summaryResponse={summaryResponse} enhancementState={enhancementState} />
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          <EnhancementStatus enhancementState={enhancementState} />

          <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-5">
            <p className="text-[10px] text-indigo-500 font-bold uppercase tracking-wider mb-1">Executive summary</p>
            <p className="text-sm font-semibold text-indigo-950 leading-relaxed">{displayValue(summary.executiveSummary)}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <ListBlock
              title="Key Strengths"
              items={summary.keyStrengths}
              tone="positive"
              emptyText="No major strengths identified from structured output."
            />
            <ListBlock
              title="Key Risks"
              items={summary.keyRisks}
              tone="risk"
              emptyText="No major risks identified from structured output."
            />
            <ListBlock
              title="Recommended Evidence"
              items={summary.recommendedEvidence}
              emptyText="No additional evidence recommendations identified from structured output."
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-slate-50 rounded-xl border border-slate-200 p-4">
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">Review route</p>
              <p className="text-sm font-bold text-slate-800">{displayValue(summary.reviewRoute)}</p>
            </div>
            <div className="bg-slate-50 rounded-xl border border-slate-200 p-4">
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">Suggested lender action</p>
              <p className="text-sm font-bold text-slate-800">{displayValue(summary.suggestedLenderAction)}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">Confidence narrative</p>
              <p className="text-[12px] font-semibold text-slate-600 leading-snug">{displayValue(summary.confidenceNarrative)}</p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">Portfolio narrative</p>
              <p className="text-[12px] font-semibold text-slate-600 leading-snug">{displayValue(summary.portfolioNarrative)}</p>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[12px] font-semibold text-slate-600">
            {displayValue(summary.numericDecisionBoundary)}
          </div>

          <DeveloperDiagnostics summaryResponse={summaryResponse} enhancementState={enhancementState} />
        </div>
      )}
    </section>
  );
}
