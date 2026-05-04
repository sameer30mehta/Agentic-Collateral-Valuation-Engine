import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import InputWizard from '../components/InputWizard';
import PropertyMap from '../components/PropertyMap';
import AgentTerminal from '../components/AgentTerminal';
import LandingHub from '../components/LandingHub';
import XAIBubble from '../components/XAIBubble';
import Stage1IntakeSection from '../components/Dashboard/Stage1IntakeSection';
import Stage2VerificationSection from '../components/Dashboard/Stage2VerificationSection';
import HistoricalReliabilitySection from '../components/Dashboard/HistoricalReliabilitySection';
import PortfolioRiskSection from '../components/Dashboard/PortfolioRiskSection';
import AIUnderwriterSummarySection from '../components/Dashboard/AIUnderwriterSummarySection';
import CaseHeader from '../components/Dashboard/CaseHeader';
import OverviewSection from '../components/Dashboard/OverviewSection';
import ValuationLiquiditySection from '../components/Dashboard/ValuationLiquiditySection';
import FinalDecisionStrip from '../components/Dashboard/FinalDecisionStrip';
import { runValuation } from '../lib/valuationEngine';
import { generateUnderwriterSummary } from '../lib/api';

const getStage1Payload = (payload) => payload?.normalizedPropertyProfile ? payload : payload?.stage1 || payload?.stage1Output || null;

const getPayloadAddress = (payload) => {
  const stage1 = getStage1Payload(payload);
  return stage1?.normalizedPropertyProfile?.address || payload?.location || 'Target';
};

const getPayloadCoordinates = (payload) => {
  const stage1 = getStage1Payload(payload);
  const profile = stage1?.normalizedPropertyProfile;
  if (Number.isFinite(profile?.lat) && Number.isFinite(profile?.lon)) return [profile.lat, profile.lon];
  return payload?.coordinates || [19.1136, 72.8697];
};

const payloadHasImages = (payload) => {
  const stage1 = getStage1Payload(payload);
  if (stage1) return (stage1.normalizedPropertyProfile?.imageCount || 0) > 0;
  return Boolean(payload?.enrichment?.images?.exterior);
};

const pickDefined = (source, keys) => keys.reduce((result, key) => {
  if (source?.[key] !== undefined && source?.[key] !== null && source?.[key] !== '') {
    result[key] = source[key];
  }
  return result;
}, {});

const firstItems = (items, limit) => Array.isArray(items) ? items.slice(0, limit) : [];

const compactStage1ForSummary = (stage1 = {}) => {
  const profile = stage1.normalizedPropertyProfile || stage1.profile || {};
  const bucketAssignment = stage1.bucketAssignment || {};
  const coarseBucket = bucketAssignment.coarseBucket || stage1.coarseBucket || {};
  const microMarketBucket = bucketAssignment.microMarketBucket || stage1.microMarketBucket || {};
  const hyperlocalContext = stage1.hyperlocalContext || {};

  return {
    normalizedPropertyProfile: pickDefined(profile, [
      'address',
      'propertyType',
      'subtype',
      'sizeSqft',
      'ageBucket',
      'legalStatus',
      'titleClarity',
      'rentalStatus',
      'occupancyStatus',
      'imageCount',
    ]),
    bucketAssignment: {
      coarseBucket: pickDefined(coarseBucket, ['id', 'label']),
      microMarketBucket: pickDefined(microMarketBucket, [
        'id',
        'label',
        'commonSizeBand',
        'liquidityNorm',
        'localPriceBand',
      ]),
    },
    hyperlocalContext: pickDefined(hyperlocalContext, ['accessQuality']),
  };
};

const compactStage2ForSummary = (stage2 = {}) => ({
  decision: stage2.decision,
  scores: stage2.scores || pickDefined(stage2, ['dataSufficiencyScore', 'anomalyScore', 'suspicionScore']),
  flags: firstItems(stage2.flags, 4),
  localReferenceContext: stage2.localReferenceContext,
  evaluationRows: firstItems(stage2.evaluationRows || stage2.evaluationTable, 4),
});

const compactHistoricalForSummary = (historical = {}) => ({
  source: historical.source,
  overallSignal: historical.overallSignal,
  confidenceAdjustment: historical.confidenceAdjustment,
  displayedCount: historical.displayedCount || historical.similarCases?.length || historical.cases?.length,
  similarCases: firstItems(historical.similarCases || historical.cases, 2).map((item) => pickDefined(item, [
    'caseId',
    'similarityScore',
    'recencyWeight',
    'confidenceContribution',
    'outcomeSummary',
  ])),
});

const compactPortfolioForSummary = (portfolio = {}) => {
  const portfolioSummary = portfolio.portfolioSummary || {};
  return {
    source: portfolio.source,
    portfolioSummary: pickDefined(portfolioSummary, [
      'riskLevel',
      'portfolioRiskScore',
      'recommendedLtv',
      'reviewRecommendation',
    ]),
    riskFlags: firstItems(portfolio.riskFlags, 4),
  };
};

const buildUnderwriterSummaryPayload = (data) => {
  const stage1 = data?.stage1 || data?.stage1Output || {};
  const stage2Output = data?.stage2Output || {};
  return {
    caseId: data?.caseId || data?.property_id || stage1?.stage1Metadata?.generatedAt || 'CURRENT_CASE',
    stage1: compactStage1ForSummary(stage1),
    stage2Output: compactStage2ForSummary(stage2Output),
    valuation: {
      marketValue: data?.marketValue,
      distressValue: data?.distressValue,
      timeToLiquidateDays: data?.timeToSell,
      confidenceScore: data?.confidence,
    },
    historicalCaseSummary: compactHistoricalForSummary(data?.historicalCaseSummary || {}),
    portfolioRiskSummary: compactPortfolioForSummary(data?.portfolioRiskSummary || {}),
    numericDecisionBoundary: 'All numeric scores, value estimates, LTV adjustments, and risk flags are computed by deterministic engines. The AI summary only explains those outputs and recommends evidence.',
  };
};

const getUnderwriterSummaryRequestKey = (data) => {
  if (!data) return null;
  return [
    data?.caseId || data?.property_id || data?.stage1?.stage1Metadata?.generatedAt || 'CURRENT_CASE',
    data?.stage1?.normalizedPropertyProfile?.address || data?.address || '',
    data?.stage1?.normalizedPropertyProfile?.sizeSqft || data?.size || data?.area || '',
    data?.stage2Output?.decision || data?.verificationDecision?.decision || '',
    data?.marketValue || ''
  ].join('|');
};

const normalizeUnderwriterSummaryResponse = (response, defaultMode = 'auto') => {
  const source = response?.source || 'unavailable';
  const mode = response?.mode || defaultMode;
  const summaryQuality = response?.summaryQuality || (
    source === 'rule_based_fallback'
      ? 'fallback'
      : mode === 'enhanced'
        ? 'enhanced'
        : mode === 'fast'
          ? 'fast'
          : 'unavailable'
  );

  return {
    source,
    modelUsed: response?.modelUsed ?? null,
    fallbackUsed: Boolean(response?.fallbackUsed),
    mode,
    summaryQuality,
    upgradeAvailable: Boolean(response?.upgradeAvailable),
    error: response?.error || null,
    summary: response?.summary || null,
    llmDebug: response?.llmDebug || null
  };
};

const isEnhancedUpgrade = (response) => (
  response?.source === 'ollama' &&
  response?.summaryQuality === 'enhanced' &&
  Boolean(response?.summary)
);

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const isDemo = searchParams.get('demo') === 'true';
  
  const [showWizard, setShowWizard] = useState(false);
  const [currentData, setCurrentData] = useState(null); 
  const [pendingPayload, setPendingPayload] = useState(null);
  
  const [fieldDataIncluded, setFieldDataIncluded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [underwriterSummary, setUnderwriterSummary] = useState(null);
  const [isUnderwriterSummaryLoading, setIsUnderwriterSummaryLoading] = useState(false);
  const [underwriterSummaryEnhancement, setUnderwriterSummaryEnhancement] = useState({ status: 'idle', message: '' });
  const underwriterSummaryRequestRef = useRef({
    key: null,
    fastPromise: null,
    enhancedPromise: null,
    enhancementTimerId: null,
    enhancedRequestStarted: false,
    enhancedSummaryCommitted: false,
    visibleSummarySource: null
  });
  const underwriterSummarySequenceRef = useRef(0);

  // Modal & Notification States
  const [toast, setToast] = useState(null); 
  const [selectedImage, setSelectedImage] = useState(null); 

  // Map Filter States
  const [showCircleRate, setShowCircleRate] = useState(false);
  const [showMetro, setShowMetro] = useState(true);
  const [showFlood, setShowFlood] = useState(false);
  const [showImpactFactors, setShowImpactFactors] = useState(true);
  
  // Dashboard Tabs State
  const [activeTab, setActiveTab] = useState('summary');

  // True CUDA Vision Backend State
  const [detectedBoxes, setDetectedBoxes] = useState({});
  const [visionStatus, setVisionStatus] = useState('idle');

  useEffect(() => {
     if (selectedImage) {
        const targetUrl = selectedImage === 'exterior' ? getImageUrl(0, defaultExterior) : 
                          selectedImage === 'living' ? getImageUrl(1, defaultLiving) : 
                          selectedImage === 'kitchen' ? getImageUrl(2, defaultKitchen) : null;
                          
        if (targetUrl && !detectedBoxes[targetUrl]) {
           const runCudaInference = async () => {
              setVisionStatus('scanning');
              try {
                 let apiRes;
                 try {
                     // Try binary transfer first
                     const res = await fetch(targetUrl);
                     const blob = await res.blob();
                     const fd = new FormData();
                     fd.append("file", blob, "image.jpg");
                     
                     apiRes = await fetch("http://localhost:8000/scan", {
                         method: "POST",
                         body: fd
                     });
                 } catch (corsErr) {
                     // If browser blocks binary extraction, send URL to Python
                     console.warn("CORS blocked blob extraction. Sending URL to backend.");
                     apiRes = await fetch("http://localhost:8000/scan", {
                         method: "POST",
                         headers: { "Content-Type": "application/json" },
                         body: JSON.stringify({ url: targetUrl })
                     });
                 }
                 
                 const apiData = await apiRes.json();
                 
                 setDetectedBoxes(prev => ({ ...prev, [targetUrl]: apiData.results }));
                 setVisionStatus('idle');
              } catch (err) {
                 console.error("CUDA Backend Offline or Failed:", err);
                 setVisionStatus('idle');
              }
           };
           runCudaInference();
        }
     }
  }, [selectedImage]);

  useEffect(() => {
    if (!currentData) {
      if (underwriterSummaryRequestRef.current.enhancementTimerId) {
        window.clearTimeout(underwriterSummaryRequestRef.current.enhancementTimerId);
      }
      setUnderwriterSummary(null);
      setIsUnderwriterSummaryLoading(false);
      setUnderwriterSummaryEnhancement({ status: 'idle', message: '' });
      underwriterSummaryRequestRef.current = {
        key: null,
        fastPromise: null,
        enhancedPromise: null,
        enhancementTimerId: null,
        enhancedRequestStarted: false,
        enhancedSummaryCommitted: false,
        visibleSummarySource: null
      };
      return;
    }

    const requestKey = getUnderwriterSummaryRequestKey(currentData);
    const summaryPayload = buildUnderwriterSummaryPayload(currentData);
    const requestSequence = underwriterSummarySequenceRef.current + 1;
    underwriterSummarySequenceRef.current = requestSequence;

    const clearEnhancementTimer = () => {
      if (!underwriterSummaryRequestRef.current.enhancementTimerId) return;
      window.clearTimeout(underwriterSummaryRequestRef.current.enhancementTimerId);
      underwriterSummaryRequestRef.current = {
        ...underwriterSummaryRequestRef.current,
        enhancementTimerId: null
      };
    };

    const startEnhancedSummary = () => {
      if (underwriterSummarySequenceRef.current !== requestSequence) return;

      const requestState = underwriterSummaryRequestRef.current;
      if (requestState.key !== requestKey || requestState.enhancedRequestStarted) return;

      clearEnhancementTimer();

      let enhancedPromise = requestState.enhancedPromise;
      if (!enhancedPromise) {
        enhancedPromise = generateUnderwriterSummary(summaryPayload, { mode: 'enhanced' });
      }

      underwriterSummaryRequestRef.current = {
        ...requestState,
        enhancedPromise,
        enhancementTimerId: null,
        enhancedRequestStarted: true
      };
      setUnderwriterSummaryEnhancement({
        status: 'enhancing',
        message: 'Enhancing summary with qwen2.5:7b...'
      });

      enhancedPromise
        .then((enhancedResult) => {
          if (underwriterSummarySequenceRef.current !== requestSequence) return;

          const normalizedEnhanced = normalizeUnderwriterSummaryResponse(enhancedResult, 'enhanced');
          if (isEnhancedUpgrade(normalizedEnhanced)) {
            underwriterSummaryRequestRef.current = {
              ...underwriterSummaryRequestRef.current,
              enhancedSummaryCommitted: true,
              visibleSummarySource: 'ollama'
            };
            setUnderwriterSummary(normalizedEnhanced);
            setUnderwriterSummaryEnhancement({
              status: 'upgraded',
              message: 'Enhanced summary replaced the fast summary.'
            });
            showToast(`AI summary upgraded with ${normalizedEnhanced.modelUsed || 'qwen2.5:7b'}.`, 'success');
            return;
          }

          const currentSummarySource = underwriterSummaryRequestRef.current.visibleSummarySource || 'unavailable';

          if (currentSummarySource === 'ollama') {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable; fast summary retained.'
            });
            showToast('Fast AI summary retained. Enhanced model was unavailable.', 'info');
          } else if (currentSummarySource === 'rule_based_fallback') {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable; rule-based fallback retained.'
            });
            showToast('Fallback AI summary retained. Enhanced model was unavailable.', 'info');
          } else {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable while the fast summary is still loading.'
            });
            showToast('Enhanced model was unavailable while the fast summary was still loading.', 'info');
          }
        })
        .catch((error) => {
          if (underwriterSummarySequenceRef.current !== requestSequence) return;
          console.warn('Enhanced AI summary unavailable; retaining current summary.', error);
          const currentSummarySource = underwriterSummaryRequestRef.current.visibleSummarySource || 'unavailable';
          if (currentSummarySource === 'ollama') {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable; fast summary retained.'
            });
            showToast('Fast AI summary retained. Enhanced model was unavailable.', 'info');
          } else if (currentSummarySource === 'rule_based_fallback') {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable; rule-based fallback retained.'
            });
            showToast('Fallback AI summary retained. Enhanced model was unavailable.', 'info');
          } else {
            setUnderwriterSummaryEnhancement({
              status: 'unavailable',
              message: 'Enhanced model unavailable while the fast summary is still loading.'
            });
            showToast('Enhanced model was unavailable while the fast summary was still loading.', 'info');
          }
        })
        .finally(() => {
          if (underwriterSummarySequenceRef.current === requestSequence) {
            underwriterSummaryRequestRef.current = {
              ...underwriterSummaryRequestRef.current,
              enhancedPromise: null,
              enhancementTimerId: null,
            };
          }
        });
    };

    let fastPromise = (
      underwriterSummaryRequestRef.current.key === requestKey
      ? underwriterSummaryRequestRef.current.fastPromise
      : null
    );

    if (!fastPromise) {
      fastPromise = generateUnderwriterSummary(summaryPayload, { mode: 'fast' });
    }

    underwriterSummaryRequestRef.current = {
      key: requestKey,
      fastPromise,
      enhancedPromise: null,
      enhancementTimerId: null,
      enhancedRequestStarted: false,
      enhancedSummaryCommitted: false,
      visibleSummarySource: null
    };
    setUnderwriterSummary(null);
    setIsUnderwriterSummaryLoading(true);
    setUnderwriterSummaryEnhancement({ status: 'idle', message: '' });

    fastPromise
      .then((result) => {
        if (underwriterSummarySequenceRef.current !== requestSequence) return;

        const fastResponse = normalizeUnderwriterSummaryResponse(result, 'fast');
        if (!underwriterSummaryRequestRef.current.enhancedSummaryCommitted) {
          underwriterSummaryRequestRef.current = {
            ...underwriterSummaryRequestRef.current,
            visibleSummarySource: fastResponse.source
          };
          setUnderwriterSummary(fastResponse);
        }
        setIsUnderwriterSummaryLoading(false);

        if (fastResponse.source === 'rule_based_fallback') {
          showToast('Fast local LLM was unavailable after the timeout; rule-based fallback is shown.', 'info');
        } else if (fastResponse.summary) {
          showToast('Fast AI underwriter summary is ready in the AI Brief tab.', 'info');
        }

        clearEnhancementTimer();
        underwriterSummaryRequestRef.current = {
          ...underwriterSummaryRequestRef.current,
          fastPromise: null,
          enhancedPromise: null,
          enhancedRequestStarted: false,
          enhancementTimerId: null
        };
        setUnderwriterSummaryEnhancement({ status: 'idle', message: '' });
      })
      .catch((error) => {
        if (underwriterSummarySequenceRef.current !== requestSequence) return;
        setUnderwriterSummary(
          normalizeUnderwriterSummaryResponse({
            source: 'unavailable',
            modelUsed: null,
            fallbackUsed: false,
            mode: 'fast',
            summaryQuality: 'unavailable',
            upgradeAvailable: false,
            error: error?.message || 'AI underwriter summary unavailable',
            summary: null
          }, 'fast')
        );
        clearEnhancementTimer();
        underwriterSummaryRequestRef.current = {
          ...underwriterSummaryRequestRef.current,
          fastPromise: null,
          enhancedPromise: null,
          enhancementTimerId: null
        };
        setUnderwriterSummaryEnhancement({ status: 'idle', message: '' });
        setIsUnderwriterSummaryLoading(false);
      })
      .finally(() => {
        if (underwriterSummarySequenceRef.current === requestSequence) {
          underwriterSummaryRequestRef.current = {
            ...underwriterSummaryRequestRef.current,
            fastPromise: null
          };
          setIsUnderwriterSummaryLoading(false);
        }
      });

    return () => {
      clearEnhancementTimer();
    };
  }, [currentData]);

  const resetUnderwriterSummary = () => {
    underwriterSummarySequenceRef.current += 1;
    if (underwriterSummaryRequestRef.current.enhancementTimerId) {
      window.clearTimeout(underwriterSummaryRequestRef.current.enhancementTimerId);
    }
    underwriterSummaryRequestRef.current = {
      key: null,
      fastPromise: null,
      enhancedPromise: null,
      enhancementTimerId: null,
      enhancedRequestStarted: false,
      enhancedSummaryCommitted: false,
      visibleSummarySource: null
    };
    setUnderwriterSummary(null);
    setIsUnderwriterSummaryLoading(false);
    setUnderwriterSummaryEnhancement({ status: 'idle', message: '' });
  };

  const handleWizardSubmit = (payload) => {
    setShowWizard(false);
    setPendingPayload(payload);
    setActiveTab('summary');
    resetUnderwriterSummary();
    setIsLoading(true); // Triggers AgentTerminal
  };
  const finalizeValuation = async () => {
    try {
      const targetCenter = getPayloadCoordinates(pendingPayload); 
      
      const results = await runValuation(pendingPayload);
      results.coordinates = targetCenter;
      
      setCurrentData(results);
      setActiveTab('summary');
      setFieldDataIncluded(payloadHasImages(pendingPayload));
    } catch (error) {
      console.error("Valuation Engine Error:", error);
      showToast("Valuation Engine crashed. Check console.", "error");
    } finally {
      setIsLoading(false);
      setPendingPayload(null);
    }
  };

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const calculateGaugeOffset = (score) => {
    return 251 - (251 * (score / 100));
  };

  const defaultExterior = "https://lh3.googleusercontent.com/aida-public/AB6AXuA1SApb750yQYbJtFHGRemWz--sEHdPwXTJr5nCpIK_cj6gKGKzRn7EHOVIynJu4gnSDq3IfgclBa-N1AYzotN_OSVnwAMma4ujpHUh6PDPe4gjWQb1MEx6gqZO4FW9Cc4WbRilA3v-rJq5JTdcCROu0y0vwZ9T6VLnU2AdSpJgX6OYZvhkgiGbtEJk51NG3_cjrWA3MU8R7JuotoyBjEjvq3_eLylkq3rv5ADbknUoRfFLNcsDjsC8P5DIRtZ9vF9z7kS7WAEPJTPv";
  const defaultLiving = "https://lh3.googleusercontent.com/aida-public/AB6AXuAjHoqaV86y19B2s3MLps2eYeM0bz5984kIaOpdLw4IvBDkDC8Ucna9rdaBgoijAwlZ5kTqU9WvU7ecUmTQixJG5IX2Ncnw2hgvZEcPBoaGf5HFE9G-_1eZ9ECF1U-5fRH_ko2gUVuoM5rwvH-GAfGTFJK--P42SyYdTSpkPZvoHuPiORe_F3HWI7JR5sWskKEZvjvPQugYLrLTFVp5ZcIUS5O7e8D5iykxzpKmWx54odKLNg2B7C3ih1NSaXzDKzI-EDBmlCcVqAU6";
  const defaultKitchen = "https://lh3.googleusercontent.com/aida-public/AB6AXuB8XGn5YwGAABpNvnbJvaA57CyQyc_Z3mlGZynB3mg1irAN1ZxTTr0ilTosQrAUIC_ELEFiXWlNwPMVxuIDSn_TQgzqWAAOxAlI_wYvLChOAVaHRutWGrkZ6UIo121roaZYD_xCgkx0mJgqXzgOOFsi0CqotflFpbDaBPHOo-Q2_mW3T53mUsn7-OJZcIQ_KZNF6UMwD4qIVzCVCIHbDMf31b3eBxx9G7xGTz9IaBCcd91Z1OW5DoUU2gkJimJHgMZv-ABprPcaEnsI";

  const getImageUrl = (index, fallback) => {
    return (currentData?.rawImages && currentData.rawImages[index]) ? currentData.rawImages[index] : fallback;
  };

  const selectedImageObj = selectedImage === 'exterior' ? getImageUrl(0, defaultExterior) : 
                           selectedImage === 'living' ? getImageUrl(1, defaultLiving) : 
                           selectedImage === 'kitchen' ? getImageUrl(2, defaultKitchen) : null;

  return (
    <div className="flex h-screen overflow-hidden relative bg-[#eef2f6]">
      {/* Toast Notification Portal */}
      {toast && (
        <div className={`fixed top-4 right-4 z-[999] px-6 py-3 rounded-lg shadow-2xl flex items-center gap-3 transition-all animate-bounce ${
          toast.type === 'success' ? 'bg-emerald-600' : toast.type === 'error' ? 'bg-red-600' : 'bg-blue-600'
        } text-white`}>
          <span className="material-symbols-outlined text-xl">
            {toast.type === 'success' ? 'check_circle' : toast.type === 'error' ? 'error' : 'info'}
          </span>
          <span className="text-sm font-semibold tracking-wide">{toast.message}</span>
        </div>
      )}

      {/* Modals & Overlays */}
      {showWizard && <InputWizard onSubmit={handleWizardSubmit} onCancel={() => setShowWizard(false)} />}

      {/* Image Annotation Modal */}
      {selectedImage && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-slate-950/90 backdrop-blur-md p-6 animate-in fade-in">
          <button 
            onClick={() => setSelectedImage(null)} 
            className="absolute top-6 right-6 text-white/50 hover:text-white transition-colors bg-white/10 p-2 rounded-full"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
          
          <div className="max-w-4xl w-full h-[80vh] relative flex flex-col justify-center items-center">
            <div className="relative inline-block border-4 border-slate-800 rounded-xl overflow-hidden shadow-[0_0_80px_rgba(0,0,0,0.5)]">
               <img src={selectedImageObj} alt="Enlarged visualization" className="max-h-[75vh] w-auto max-w-full object-contain" />
              {/* Active ML Bounding Boxes mapping */}
              {selectedImageObj && detectedBoxes[selectedImageObj] && detectedBoxes[selectedImageObj].map((box, idx) => {
                 return (
                  <div key={idx} style={{ 
                      top: `${box.top_pct}%`, left: `${box.left_pct}%`, width: `${box.width_pct}%`, height: `${box.height_pct}%` 
                  }} className="absolute border-2 shadow-sm pointer-events-none rounded transition-all flex justify-center border-red-500 bg-red-500/10">
                    <span className="absolute -top-7 whitespace-nowrap px-2 py-0.5 text-xs font-bold text-white rounded shadow-sm bg-red-500">
                      CUDA: {box.label} ({Math.round(box.score * 100)}%)
                    </span>
                  </div>
                 );
              })}
              
              {visionStatus === 'scanning' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-md text-white font-mono flex-col gap-3 rounded-xl z-50">
                      <div className="w-10 h-10 rounded-full border-4 border-amber-500 border-t-transparent animate-spin"></div>
                      <p className="font-bold text-amber-500 tracking-widest text-sm">RTX BLACKWELL DETECTING...</p>
                  </div>
              )}
              
            </div>
            <p className="text-emerald-400 mt-4 font-mono text-sm">
                {visionStatus === 'scanning' ? "Vision Agent processing matrix... Do not close." : 
                 (detectedBoxes[selectedImageObj] ? `Analysis Complete: Detected ${detectedBoxes[selectedImageObj].length} Risk Element(s)` : "Vision Agent Diagnostics Connected")}
            </p>
          </div>
        </div>
      )}

      {/* Main Content Wrapper */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* TopNavBar */}
        <header className="z-50 flex w-full items-center justify-between border-b border-slate-200 bg-white px-5 py-4 md:px-8">
          <div className="flex items-center gap-5">
            <div>
              <h1 className="text-xl font-black tracking-tight text-slate-950">PropScore</h1>
              <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">Collateral intelligence</p>
            </div>
            <span className="hidden items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-emerald-700 md:flex">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              Deterministic engines active
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-3 text-[12px] font-bold uppercase tracking-wider text-slate-500 lg:flex">
              <span>Local SQLite</span>
              <span className="h-1 w-1 rounded-full bg-slate-300"></span>
              <span>FastAPI</span>
              <span className="h-1 w-1 rounded-full bg-slate-300"></span>
              <span>Ollama optional</span>
            </div>
            <button
              onClick={() => setShowWizard(true)}
              className="flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white shadow-sm transition-colors hover:bg-slate-800"
            >
              <span className="material-symbols-outlined text-[18px]">add</span>
              New Case
            </button>
          </div>
        </header>

        {/* Scrollable Content */}
        <main className="flex-1 overflow-y-auto p-5 pb-32 transition-opacity duration-300 relative bg-[#eef2f6] md:p-8">
          
          {isLoading && pendingPayload && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-50/90 backdrop-blur-md px-4 py-6">
              <div className="w-full max-w-4xl">
              <div className="mb-5 flex flex-col items-center text-center">
                 <div className="w-12 h-12 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin mb-3"></div>
                 <h2 className="text-xl font-bold font-headline text-slate-800">Generating collateral intelligence</h2>
                 <p className="text-sm text-slate-500">The deterministic valuation and verification pipeline is running.</p>
              </div>
              <AgentTerminal 
              isActive={isLoading} 
              locationName={getPayloadAddress(pendingPayload).split(',')[0]} 
              hasImages={payloadHasImages(pendingPayload)}
              externalLog={visionStatus.startsWith('Downloading') ? visionStatus : null}
              blockComplete={visionStatus.startsWith('Downloading')}
              onComplete={finalizeValuation} 
            />
              </div>
            </div>
          )}

          {!currentData && !isLoading ? (
             <LandingHub onInitialize={() => setShowWizard(true)} />
          ) : (
             currentData && (
              <div className={`max-w-7xl mx-auto space-y-6 ${isLoading ? 'opacity-0 scale-95 transition-all' : 'opacity-100 scale-100 transition-all duration-500'}`}>
                <CaseHeader
                  data={currentData}
                  aiStatus={
                    isUnderwriterSummaryLoading
                      ? 'Generating'
                      : underwriterSummaryEnhancement.status === 'enhancing'
                        ? 'Enhancing'
                        : underwriterSummary?.summaryQuality || 'Pending'
                  }
                />
                
                {/* Clean Tab Navigation */}
                <div className="sticky top-0 z-30 rounded-xl border border-slate-200 bg-white/95 p-2 shadow-sm backdrop-blur">
                  <div className="flex gap-1.5 overflow-x-auto">
                  {[
                    { id: 'summary', label: 'Overview', icon: 'monitoring' },
                    { id: 'intake', label: 'Stage 1 Buckets', icon: 'rule_settings' },
                    { id: 'verification', label: 'Stage 2 Verification', icon: 'fact_check' },
                    { id: 'valuation', label: 'Valuation', icon: 'payments' },
                    { id: 'history', label: 'Historical Cases', icon: 'history' },
                    { id: 'portfolio', label: 'Portfolio Risk', icon: 'account_balance' },
                    {
                      id: 'ai',
                      label: 'AI Brief',
                      icon: 'psychology',
                      status: isUnderwriterSummaryLoading
                        ? 'Fast'
                        : underwriterSummaryEnhancement.status === 'scheduled'
                          ? 'Queued'
                        : underwriterSummaryEnhancement.status === 'enhancing'
                          ? 'Enhancing'
                          : underwriterSummaryEnhancement.status === 'upgraded'
                            ? 'Enhanced'
                            : underwriterSummary?.summary
                              ? 'Ready'
                              : null
                    },
                    { id: 'analysis', label: 'Visual Evidence', icon: 'camera_enhance' },
                    { id: 'location', label: 'Map Intelligence', icon: 'public' }
                  ].map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`px-3 py-2 text-sm font-bold rounded-lg transition-colors flex items-center gap-2 whitespace-nowrap shrink-0 ${
                        activeTab === tab.id 
                          ? 'text-white bg-slate-950 border border-slate-950 shadow-sm' 
                          : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[18px]">{tab.icon}</span>
                      {tab.label}
                      {tab.status && (
                        <span className="ml-1 px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 text-[9px] font-black uppercase tracking-widest">
                          {tab.status}
                        </span>
                      )}
                    </button>
                  ))}
                  </div>
                </div>

                {activeTab === 'summary' && (
                  <OverviewSection
                    data={currentData}
                    underwriterSummary={underwriterSummary}
                    isUnderwriterSummaryLoading={isUnderwriterSummaryLoading}
                  />
                )}

                {activeTab === 'intake' && <Stage1IntakeSection stage1={currentData.stage1} />}

                {activeTab === 'verification' && <Stage2VerificationSection stage2Output={currentData.stage2Output} />}

                {activeTab === 'valuation' && <ValuationLiquiditySection data={currentData} />}

                {activeTab === 'history' && <HistoricalReliabilitySection historicalCaseSummary={currentData.historicalCaseSummary} />}

                {activeTab === 'portfolio' && <PortfolioRiskSection portfolioRiskSummary={currentData.portfolioRiskSummary} />}

                {activeTab === 'ai' && (
                  <AIUnderwriterSummarySection
                    summaryResponse={underwriterSummary}
                    isLoading={isUnderwriterSummaryLoading}
                    enhancementState={underwriterSummaryEnhancement}
                  />
                )}

                {false && activeTab === 'summary' && (
                  <>
                    {/* Decision Banner Row */}
                    <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between mt-2">
                   <div className="flex items-start md:items-center gap-4">
                      <div className={`w-14 h-14 rounded-full flex items-center justify-center shrink-0 ${
                         currentData.verificationDecision.decision.includes('REJECT') ? 'bg-red-100 text-red-600' : 
                         currentData.verificationDecision.decision.includes('MANUAL') ? 'bg-amber-100 text-amber-600' :
                         currentData.verificationDecision.decision.includes('PENALTY') ? 'bg-amber-100 text-amber-600' :
                         currentData.verificationDecision.decision.includes('WARNING') ? 'bg-blue-100 text-blue-600' :
                         'bg-emerald-100 text-emerald-600'
                      }`}>
                         <span className="material-symbols-outlined text-3xl">
                           {currentData.verificationDecision.decision.includes('REJECT') ? 'cancel' : 
                            currentData.verificationDecision.decision.includes('MANUAL') ? 'policy' : 
                            'check_circle'}
                         </span>
                      </div>
                      <div>
                         <h3 className="text-[11px] font-bold tracking-wider uppercase text-slate-400 mb-1 flex items-center gap-2">
                           Verification Engine Output 
                           <XAIBubble title="Decision Matrix">
                             <p>Final system outcome computed from cross-signal anomalies, data sufficiency, and blocking flags.</p>
                             <ul className="mt-2 text-xs space-y-1 text-slate-600">
                                <li><strong>ACCEPT_CLEAN:</strong> Suspicion &le; 20</li>
                                <li><strong>ACCEPT_WARNING:</strong> Suspicion &le; 40</li>
                                <li><strong>ACCEPT_CONFIDENCE_PENALTY:</strong> Suspicion &le; 70</li>
                                <li><strong>MANUAL_REVIEW:</strong> Suspicion &gt; 70</li>
                                <li><strong>REJECT_BLOCK:</strong> Critical Zoning or Legal Flag</li>
                             </ul>
                           </XAIBubble>
                         </h3>
                         <h2 className={`text-xl font-bold font-headline ${
                            currentData.verificationDecision.decision.includes('REJECT') ? 'text-red-700' : 
                            currentData.verificationDecision.decision.includes('MANUAL') ? 'text-amber-700' :
                            currentData.verificationDecision.decision.includes('PENALTY') ? 'text-amber-700' :
                            currentData.verificationDecision.decision.includes('WARNING') ? 'text-blue-700' :
                            'text-emerald-700'
                         }`}>{currentData.verificationDecision.label}</h2>
                         <p className="text-sm font-medium text-slate-600 mt-1 max-w-2xl">{currentData.verificationDecision.explanation}</p>
                      </div>
                   </div>
                   <div className="flex flex-col items-start md:items-end md:border-l border-slate-100 md:pl-6 mt-4 md:mt-0 shrink-0">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                        Suspicion Score
                        <XAIBubble title="Inconsistency Scoring">
                           <p>Weighted sum of anomaly scores. Multiplied by 1.3x if signals diverge across 3+ orthogonal sources (e.g. vision, location, market norms).</p>
                        </XAIBubble>
                      </span>
                      <span className={`text-3xl font-mono font-bold ${currentData.anomalyResults.suspicionScore > 40 ? 'text-red-500' : currentData.anomalyResults.suspicionScore > 20 ? 'text-amber-500' : 'text-emerald-500'}`}>
                         {currentData.anomalyResults.suspicionScore}/100
                      </span>
                      <span className="text-[9px] font-bold text-slate-400 mt-1 uppercase">
                         Data Sufficiency: {(currentData.dataSufficiency * 10).toFixed(1)}/10
                      </span>
                   </div>
                </div>

                {/* Top Row: Overview, PropScore, Metrics */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Case Overview */}
                  <div className="bg-white rounded-xl p-6 flex flex-col justify-between border border-slate-200 shadow-sm relative overflow-hidden">
                    <div className="absolute -right-10 -top-10 text-slate-50 opacity-50 pointer-events-none">
                       <span className="material-symbols-outlined text-[150px]">data_object</span>
                    </div>
                    <div className="relative z-10">
                      <div className="flex justify-between items-start mb-4">
                        <h3 className="text-headline-sm font-headline font-bold text-slate-800">Coordinator Output</h3>
                        <span className="bg-emerald-50 text-emerald-600 border border-emerald-200 text-[10px] font-bold px-2 py-1 rounded shadow-sm uppercase tracking-wider flex items-center gap-1" title="Geospatial resolution via Komoot Photon API with circle rate interpolation">
                           <span className="material-symbols-outlined text-[12px]">verified_user</span> Sync Complete
                        </span>
                      </div>
                      <h4 className="text-lg font-headline font-bold text-indigo-700 mb-1">
                        {currentData.caseDetails.address.split(',').slice(0, 2).join(',')}
                      </h4>
                      <p className="text-slate-500 text-sm font-body mb-6">
                        {currentData.caseDetails.address.split(',').slice(2).join(',')}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-y-4 gap-x-2 relative z-10">
                      <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Asset Type</p>
                        <p className="text-sm font-medium text-slate-800">{currentData.caseDetails.type}</p>
                      </div>
                      <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Config</p>
                        <p className="text-sm font-medium text-slate-800">{currentData.caseDetails.config}</p>
                      </div>
                      <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Area</p>
                        <p className="text-sm font-medium text-slate-800">{currentData.caseDetails.area} sqft</p>
                      </div>
                      <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Computed Age</p>
                        <p className="text-sm font-medium text-slate-800">{currentData.caseDetails.age}</p>
                      </div>
                    </div>
                  </div>

                  {/* PropScore Gauge */}
                  <div className="bg-white rounded-xl p-6 flex flex-col items-center relative overflow-hidden border border-slate-200 shadow-sm">
                    <h3 className="text-headline-sm font-headline font-bold text-slate-800 self-start mb-4 flex items-center gap-2">
                       Resale Liquidity Index
                       <XAIBubble title="Resale Potential Index (0–100)">
                         <p>A consolidated liquidity signal derived from multiple orthogonal factors:</p>
                         <div className="mt-2 space-y-1.5 text-xs">
                           <div className="flex items-center gap-2"><span className="text-emerald-500">↑</span> <span>Prime location & infrastructure proximity</span></div>
                           <div className="flex items-center gap-2"><span className="text-emerald-500">↑</span> <span>Standard configuration (e.g. 2BHK) — max fungibility</span></div>
                           <div className="flex items-center gap-2"><span className="text-emerald-500">↑</span> <span>High demand micro-market absorption rate</span></div>
                           <div className="flex items-center gap-2"><span className="text-red-400">↓</span> <span>Older construction (&gt;15 yrs) — depreciation penalty</span></div>
                           <div className="flex items-center gap-2"><span className="text-red-400">↓</span> <span>Legal complexity — suppresses buyer confidence</span></div>
                           <div className="flex items-center gap-2"><span className="text-red-400">↓</span> <span>Niche asset profile — smaller buyer pool</span></div>
                         </div>
                         <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-bold text-center">
                           <div className="bg-emerald-50 text-emerald-700 rounded-lg py-1.5">80–100 Liquid</div>
                           <div className="bg-amber-50 text-amber-700 rounded-lg py-1.5">50–80 Moderate</div>
                           <div className="bg-red-50 text-red-600 rounded-lg py-1.5">&lt;50 Illiquid</div>
                         </div>
                       </XAIBubble>
                    </h3>
                    <div className="relative w-40 h-40 flex items-center justify-center mt-2 mb-6">
                      <svg className="w-full h-full transform -rotate-90 transition-all duration-700" viewBox="0 0 100 100">
                        <circle className="text-slate-100" cx="50" cy="50" fill="none" r="40" stroke="currentColor" strokeDasharray="251" strokeDashoffset="0" strokeWidth="12"></circle>
                        <circle cx="50" cy="50" fill="none" r="40" stroke="url(#gradient)" strokeDasharray="251" strokeDashoffset={calculateGaugeOffset(currentData.propScore)} strokeLinecap="round" strokeWidth="12" className="transition-all duration-1000 ease-out"></circle>
                        <defs>
                          <linearGradient id="gradient" x1="0%" x2="100%" y1="0%" y2="100%">
                            <stop offset="0%" stopColor={currentData.propScore < 50 ? "#ef4444" : "#4f46e5"}></stop>
                            <stop offset="100%" stopColor={currentData.propScore < 50 ? "#fca5a5" : "#8b5cf6"}></stop>
                          </linearGradient>
                        </defs>
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className={`text-4xl font-headline font-bold transition-colors ${currentData.propScore < 50 ? 'text-red-500' : 'text-indigo-600'}`}>{currentData.propScore}</span>
                      </div>
                    </div>
                    <div className={`rounded-full px-4 py-1.5 text-xs font-bold mb-4 relative z-10 ${currentData.propScore < 50 ? 'bg-red-50 text-red-600 border border-red-200' : 'bg-indigo-50 text-indigo-700 border border-indigo-200'}`}>
                      {currentData.propScore < 50 ? 'High Distress Risk' : currentData.propScore < 75 ? 'Moderate Liquidity' : 'Prime Asset Status'}
                    </div>
                    
                    <div className="w-full mt-auto">
                      <div className="flex justify-between items-center text-[10px] font-bold tracking-wider uppercase text-slate-400 mb-1">
                        <span>Agent Confidence Index</span>
                        <span className="text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded">{currentData.confidence.toFixed(2)}</span>
                      </div>
                      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden flex relative shadow-inner">
                        <div className="h-full bg-slate-300" style={{ width: `${currentData.confidenceBreakdown.base * 100}%` }}></div>
                        <div className="h-full bg-indigo-400" style={{ width: `${currentData.confidenceBreakdown.legal * 100}%` }}></div>
                        {currentData.confidenceBreakdown.visual > 0 && (
                          <div className="h-full bg-emerald-400" style={{ width: `${currentData.confidenceBreakdown.visual * 100}%` }}></div>
                        )}
                        {currentData.confidenceBreakdown.historical > 0 && (
                          <div className="h-full bg-teal-400" style={{ width: `${currentData.confidenceBreakdown.historical * 100}%` }}></div>
                        )}
                      </div>
                      {currentData.historicalCaseSummary && (
                        <p className="text-[10px] text-slate-400 font-semibold mt-2">
                          Historical layer: {currentData.confidenceBreakdown.historicalDelta > 0 ? '+' : ''}{currentData.confidenceBreakdown.historicalDelta.toFixed(2)}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Key Metrics */}
                  <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex flex-col justify-center relative">
                    <h3 className="text-headline-sm font-headline font-bold text-slate-800 mb-6 flex items-center gap-2">
                       <span className="material-symbols-outlined text-indigo-500">monitoring</span>
                       Market Agent Projections
                       <XAIBubble title="Valuation Methodology">
                         <p className="font-semibold text-slate-800 mb-2">Market Value Estimation</p>
                         <p>Not a single regression. Market Value is a composite function of:</p>
                         <div className="bg-slate-50 rounded-lg p-3 font-mono text-xs text-slate-600 mt-2 leading-relaxed border border-slate-100">
                           Market_Value = f(circle_rate, location_premium, property_type, area, age_depreciation, infra_score, rental_yield)
                         </div>
                         <p className="font-semibold text-slate-800 mt-4 mb-2">Distress Sale Value</p>
                         <div className="bg-slate-50 rounded-lg p-3 font-mono text-xs text-slate-600 leading-relaxed border border-slate-100">
                           Distress = Market_Value × Liquidity_Discount(asset_type, demand, legal_clarity)
                         </div>
                         <p className="mt-3 text-xs text-slate-400">Output is always a range, not a point estimate.</p>
                       </XAIBubble>
                    </h3>
                    <div className="space-y-6">
                      <div className="pb-4 border-b border-slate-100 last:border-0 last:pb-0">
                        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Base Market Value</p>
                        <p className="text-2xl font-mono text-indigo-700 font-bold">{currentData.marketValue}</p>
                      </div>
                      <div className="pb-4 border-b border-slate-100 last:border-0 last:pb-0">
                        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1 flex justify-between">
                           Distressed Default Value
                           <span className="text-red-500 flex items-center"><span className="material-symbols-outlined text-[14px]">warning</span></span>
                        </p>
                        <p className="text-xl font-mono text-slate-800 font-medium">{currentData.distressValue}</p>
                      </div>
                      <div className="pb-4 border-b border-slate-100 last:border-0 last:pb-0">
                        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Projected Time to Sell</p>
                        <p className="text-lg font-mono text-slate-600 font-medium bg-slate-50 px-2 py-1 rounded inline-block">{currentData.timeToSell}</p>
                      </div>
                    </div>
                  </div>
                </div>
                </>
                )}

                {/* Middle Row: Drivers, Visual Audit */}
                {activeTab === 'analysis' && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
                  {/* Value Drivers */}
                  <div className="space-y-6 lg:col-span-1 h-full">
                    <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm h-full min-h-[410px] flex flex-col">
                      <h3 className="text-sm font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2 flex items-center justify-between">
                         Valuation Drivers
                         <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] rounded font-mono border border-indigo-100">MARKET_AGENT</span>
                      </h3>
                      <ul className="space-y-4 flex-1">
                        {currentData.drivers.map((driver, idx) => (
                          <li key={idx} className="flex items-start gap-3">
                            <div className={`w-8 h-8 rounded-lg shrink-0 flex items-center justify-center ${driver.positive ? 'bg-emerald-50 text-emerald-600 border border-emerald-100' : 'bg-red-50 text-red-500 border border-red-100'}`}>
                               <span className="material-symbols-outlined text-[18px]">
                                 {driver.positive ? 'trending_up' : 'trending_down'}
                               </span>
                            </div>
                            <div>
                              <p className="font-bold text-[13px] leading-tight text-slate-700">{driver.name}</p>
                              <p className={`text-[12px] font-bold mt-0.5 ${driver.positive ? 'text-emerald-600' : 'text-red-500'}`}>{driver.impact}</p>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* AI Visual Audit */}
                  <div className="bg-white rounded-xl p-6 lg:col-span-2 border border-slate-200 shadow-sm flex flex-col relative overflow-hidden h-full">
                    <div className="flex justify-between items-center mb-2 relative z-10">
                      <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-500">camera_enhance</span>
                        Visual Evidence Review
                        <XAIBubble title="Hardware-Accelerated Vision Pipeline">
                          <p>Property images are analysed by a zero-shot object detection transformer running natively on your GPU:</p>
                          <div className="bg-slate-50 rounded-lg p-3 font-mono text-xs text-slate-600 mt-2 space-y-1 border border-slate-100">
                            <div>Model: <span className="text-indigo-600">google/owlvit-base-patch32</span></div>
                            <div>Runtime: <span className="text-indigo-600">CUDA PyTorch</span></div>
                            <div>Hardware: <span className="text-indigo-600">NVIDIA RTX (Blackwell)</span></div>
                          </div>
                          <p className="mt-3">Detects structural fractures, water damage, wall cracks, and degradation markers. Detection confidence is factored into the final valuation as a depreciation penalty.</p>
                          <p className="mt-2 text-xs text-slate-400">All inference runs locally — zero data leaves your network.</p>
                        </XAIBubble>
                      </h3>
                      <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest border ${fieldDataIncluded ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-50 text-slate-500 border-slate-200'}`}>
                         {fieldDataIncluded ? 'VERIFIED CNN RUN' : 'FALLBACK EXTRAPOLATION'}
                      </span>
                    </div>

                    <div className="flex-1 flex flex-col justify-between relative z-10">
                       <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                         <div className="group relative rounded-xl overflow-hidden isolate bg-slate-900 cursor-pointer shadow-md" onClick={() => setSelectedImage('exterior')}>
                           <img alt="Exterior" className="w-full h-[150px] object-cover transition-all duration-300 group-hover:scale-105 opacity-80 group-hover:opacity-100" src={getImageUrl(0, defaultExterior)}/>
                           <div className="absolute inset-0 border border-white/10 rounded-xl pointer-events-none"></div>
                           <div className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/60 rounded text-[9px] text-emerald-400 font-mono flex items-center gap-1 backdrop-blur-sm">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Scanned
                           </div>
                           <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-white/20 p-1 rounded-full backdrop-blur"><span className="material-symbols-outlined text-white text-[16px]">fullscreen</span></div>
                           <div className="absolute bottom-3 left-3 right-3 flex flex-col justify-end">
                             <p className="text-white font-bold text-[14px]">Exterior Analysis</p>
                           </div>
                         </div>
                         <div className="group relative rounded-xl overflow-hidden isolate bg-slate-900 cursor-pointer shadow-md" onClick={() => setSelectedImage('living')}>
                            <img alt="Living Area" className="w-full h-[150px] object-cover transition-all duration-300 group-hover:scale-105 opacity-80 group-hover:opacity-100" src={getImageUrl(1, defaultLiving)}/>
                           <div className="absolute inset-0 border border-white/10 rounded-xl pointer-events-none"></div>
                           <div className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/60 rounded text-[9px] text-emerald-400 font-mono flex items-center gap-1 backdrop-blur-sm">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Scanned
                           </div>
                           <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-white/20 p-1 rounded-full backdrop-blur"><span className="material-symbols-outlined text-white text-[16px]">fullscreen</span></div>
                           <div className="absolute bottom-3 left-3 right-3 flex flex-col justify-end">
                             <p className="text-white font-bold text-[14px]">Living Area Quality</p>
                           </div>
                         </div>
                         <div className="group relative rounded-xl overflow-hidden isolate bg-slate-900 cursor-pointer shadow-md" onClick={() => setSelectedImage('kitchen')}>
                           <img alt="Kitchen" className="w-full h-[150px] object-cover transition-all duration-300 group-hover:scale-105 opacity-80 group-hover:opacity-100" src={getImageUrl(2, defaultKitchen)}/>
                           <div className="absolute inset-0 border border-white/10 rounded-xl pointer-events-none"></div>
                           <div className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/60 rounded text-[9px] text-emerald-400 font-mono flex items-center gap-1 backdrop-blur-sm">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Scanned
                           </div>
                           <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-white/20 p-1 rounded-full backdrop-blur"><span className="material-symbols-outlined text-white text-[16px]">fullscreen</span></div>
                           <div className="absolute bottom-3 left-3 right-3 flex flex-col justify-end">
                             <p className="text-white font-bold text-[14px]">Feature Extraction</p>
                           </div>
                         </div>
                       </div>

                       {/* Agent Text Results Mapping */}
                       <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-slate-50 border border-slate-200 p-5 rounded-xl shadow-inner font-mono text-sm relative">
                          <div className="absolute -top-3 left-6 px-2 py-0.5 bg-slate-700 text-white text-[9px] font-bold rounded shadow-md tracking-widest">VISION AGENT LOGS</div>
                          <div className="flex flex-col mt-2">
                             <h4 className="flex items-center gap-1.5 text-[11px] font-bold tracking-wider uppercase text-slate-500 mb-2 font-sans">
                                 <span className="material-symbols-outlined text-[14px]">health_and_safety</span>Damage Extractor
                             </h4>
                             <div className="flex-col flex">
                                <span className={`text-[10px] font-bold px-1 py-0.5 rounded w-max mb-2 font-sans ${currentData.visualAudit.conditionScore < 7 ? 'bg-red-500 text-white' : 'bg-emerald-500 text-white'}`}>Score: {currentData.visualAudit.conditionScore}/10</span>
                                <p className="text-[11px] text-slate-600 leading-snug">› {currentData.visualAudit.conditionFindings}</p>
                             </div>
                          </div>
                          
                          <div className="flex flex-col border-l border-slate-200 pl-6 mt-2">
                             <h4 className="flex items-center gap-1.5 text-[11px] font-bold tracking-wider uppercase text-slate-500 mb-2 font-sans">
                                 <span className="material-symbols-outlined text-[14px]">verified</span>Quality Classifier
                             </h4>
                             <div className="flex-col flex">
                                <p className="text-[11px] text-slate-600 leading-snug mt-[22px]">› {currentData.visualAudit.qualityFindings}</p>
                             </div>
                          </div>

                          <div className="flex flex-col border-l border-slate-200 pl-6 mt-2">
                             <h4 className="flex items-center gap-1.5 text-[11px] font-bold tracking-wider uppercase text-slate-500 mb-2 font-sans">
                                 <span className="material-symbols-outlined text-[14px]">search_insights</span>Entity Decoder
                             </h4>
                             <div className="flex-col flex">
                                <p className="text-[11px] text-slate-600 leading-snug mt-[22px]">› {currentData.visualAudit.featuresFindings}</p>
                             </div>
                          </div>
                       </div>
                    </div>
                  </div>
                </div>
                )}

                {/* Bottom Row: Map */}
                {activeTab === 'location' && (
                <div className="bg-white rounded-xl p-6 w-full border border-slate-200 shadow-sm mb-8 relative z-0">
                   <div className="flex justify-between items-center mb-2">
                      <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                         <span className="material-symbols-outlined text-indigo-500">public</span>
                         Hyperlocal Map Intelligence
                         <XAIBubble title="Location Intelligence Engine">
                           <p>Address is resolved to precise coordinates using the <span className="font-semibold text-slate-800">Komoot Photon</span> geocoder backed by OpenStreetMap data.</p>
                           <div className="bg-slate-50 rounded-lg p-3 font-mono text-xs text-slate-600 mt-2 space-y-1 border border-slate-100">
                             <div>Geocoder: <span className="text-indigo-600">Photon (Komoot)</span></div>
                             <div>Data: <span className="text-indigo-600">OpenStreetMap</span></div>
                             <div>Proximity: <span className="text-indigo-600">Haversine distance</span></div>
                           </div>
                           <p className="mt-3">Infrastructure proximity (metro, highway, commercial hubs) is calculated using Haversine distance formulas. Circle rate zones are interpolated from government registry benchmarks to establish the statutory floor value.</p>
                         </XAIBubble>
                      </h3>
                      <div className="flex flex-wrap justify-end gap-2 max-w-lg">
                         <button onClick={() => setShowCircleRate(!showCircleRate)} className={`px-3 py-1 text-[11px] border rounded-full transition-colors font-bold flex items-center gap-1 ${showCircleRate ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'}`}>
                            <span className={`w-2 h-2 rounded-full ${showCircleRate ? 'bg-indigo-500' : 'bg-slate-300'}`}></span> Zone
                         </button>
                         <button onClick={() => setShowMetro(!showMetro)} className={`px-3 py-1 text-[11px] border rounded-full transition-colors font-bold flex items-center gap-1 ${showMetro ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'}`}>
                            <span className={`w-2 h-2 rounded-full ${showMetro ? 'bg-emerald-500' : 'bg-slate-300'}`}></span> Metro
                         </button>
                         <button onClick={() => setShowImpactFactors(!showImpactFactors)} className={`px-3 py-1 text-[11px] border rounded-full transition-colors font-bold flex items-center gap-1 shadow-sm ${showImpactFactors ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                            <span className={`w-2 h-2 rounded-full ${showImpactFactors ? 'bg-indigo-500' : 'bg-slate-300'}`}></span> Collateral Signals
                         </button>
                      </div>
                   </div>

                   <PropertyMap 
                     center={currentData.coordinates} 
                     showCircleRate={showCircleRate} 
                     showMetro={showMetro} 
                     showFlood={showFlood} 
                     showImpactFactors={showImpactFactors}
                     hyperlocalPOIs={currentData.hyperlocalContext?.pois || []}
                   />
                </div>
                )}

              </div>
             )
          )}
        </main>

        {/* Bottom Decision Bar */}
        {currentData && !isLoading && (
          <FinalDecisionStrip
            data={currentData}
            underwriterSummary={underwriterSummary}
          />
        )}

      </div>
    </div>
  );
}
