import { useEffect, useState, type FormEvent } from 'react';
import { DemoApiError, MAX_QUESTION_LENGTH, citationsForCommit, localDemoApi, type LocalDemoMeta, type LocalDemoResponse } from './api';
import './demo.css';

type MetaState = 'loading' | 'ready' | 'error';

function statusText(meta: LocalDemoMeta | null) {
  if (!meta) return 'Yerel model durumu doğrulanmadı.';
  if (meta.model_status === 'ready') return 'Yerel model hazır';
  if (meta.model_status === 'loading') return 'Yerel model yükleniyor';
  return 'Yerel model kullanılamıyor';
}

export function LocalDemoPage() {
  const [meta, setMeta] = useState<LocalDemoMeta | null>(null);
  const [metaState, setMetaState] = useState<MetaState>('loading');
  const [metaError, setMetaError] = useState('');
  const [metaAttempt, setMetaAttempt] = useState(0);
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<LocalDemoResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [requestError, setRequestError] = useState('');
  const [retryAllowed, setRetryAllowed] = useState(false);

  useEffect(() => {
    let active = true;
    setMetaState('loading'); setMetaError('');
    localDemoApi.getMeta().then((data) => {
      if (!active) return;
      setMeta(data); setMetaState('ready');
    }).catch((error: unknown) => {
      if (!active) return;
      setMeta(null); setMetaState('error');
      setMetaError(error instanceof DemoApiError ? error.message : 'Yerel demo servisi kullanılamıyor.');
    });
    return () => { active = false; };
  }, [metaAttempt]);

  async function ask(text: string) {
    setPending(true); setRequestError(''); setRetryAllowed(false);
    try {
      const result = await localDemoApi.ask(text);
      if (!meta || result.commit_sha !== meta.commit_sha) throw new DemoApiError('Yanıt, açık olan demo kaynak sürümüyle eşleşmiyor; kaynaklar gösterilmedi.', true);
      setResponse(result);
    } catch (error) {
      setResponse(null);
      setRequestError(error instanceof DemoApiError ? error.message : 'Yerel model yanıtı alınamadı.');
      setRetryAllowed(error instanceof DemoApiError ? error.retryable : true);
    } finally { setPending(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || trimmed.length > MAX_QUESTION_LENGTH || meta?.model_status !== 'ready' || pending) return;
    setResponse(null);
    void ask(trimmed);
  }

  return <section className="local-demo-page">
    <header className="local-demo-heading"><div><p className="eyebrow">ARIADNE · LOCAL AI</p><h1>Yerel demo</h1><p>Örnek kod deposu hakkında tek soru sorun. Yanıt hazırsa yerel modelden gelir ve kaynak satırlarına bağlanır.</p></div><span className={`local-demo-status model-${meta?.model_status ?? metaState}`}><i aria-hidden="true"/>{statusText(meta)}</span></header>
    <div className="local-demo-trust"><strong>Paketlenmiş örnek depo</strong><span>Demo yalnızca bu bilgisayardaki, loopback adresindeki servise bağlanır. GitHub oturumu veya gerçek kullanıcı deposu kullanılmaz.</span><span className="local-demo-origin">{meta?.data_origin === 'bundled_synthetic' ? 'Sentetik / paketlenmiş veri' : 'Veri kaynağı doğrulanmadı'}</span></div>
    {metaState === 'loading' && <div className="local-demo-notice" role="status" aria-busy="true"><span className="loading-orbit"/>Yerel demo ve model durumu denetleniyor…</div>}
    {metaState === 'error' && <div className="local-demo-notice local-demo-error" role="alert"><div><strong>Yerel demo servisi kullanılamıyor</strong><p>{metaError}</p></div><button className="subtle-button" type="button" onClick={() => setMetaAttempt((value) => value + 1)}>Yeniden dene</button></div>}
    {metaState === 'ready' && meta?.model_status === 'loading' && <div className="local-demo-notice" role="status"><span className="loading-orbit"/>Model yükleniyor. Hazır olduğunda soru alanı açılacak.</div>}
    {metaState === 'ready' && meta?.model_status === 'unavailable' && <div className="local-demo-notice local-demo-error" role="status"><div><strong>Yerel model hazır değil</strong><p>API erişilebilir, ancak model worker şu anda hazır değil. Yanıt üretilmedi.</p></div><button className="subtle-button" type="button" onClick={() => setMetaAttempt((value) => value + 1)}>Durumu yenile</button></div>}
    <div className="local-demo-columns">
      <form className="local-demo-question" onSubmit={submit}>
        <div className="demo-section-heading"><div><span className="section-kicker">ONE CODE QUESTION</span><h2>Depoya sorun</h2></div><span className="local-demo-lock">Yalnızca bu oturum</span></div>
        <label htmlFor="local-demo-question">Sorunuz</label>
        <textarea id="local-demo-question" value={question} maxLength={MAX_QUESTION_LENGTH} onChange={(event) => setQuestion(event.target.value)} placeholder="Örnek depodaki sipariş akışı hangi dosyalardan geçiyor?" aria-describedby="local-demo-question-help local-demo-question-count" disabled={pending || metaState !== 'ready' || meta?.model_status !== 'ready'}/>
        <div className="local-demo-form-footer"><small id="local-demo-question-help">Soru yerel model worker’a gönderilir; özel repo veya kimlik bilgisi eklemeyin.</small><span id="local-demo-question-count" aria-live="polite">{question.length}/{MAX_QUESTION_LENGTH}</span></div>
        <button className="primary-button" type="submit" disabled={!question.trim() || question.trim().length > MAX_QUESTION_LENGTH || pending || metaState !== 'ready' || meta?.model_status !== 'ready'}>{pending ? <><span className="button-spinner"/> Yanıt hazırlanıyor…</> : 'Soruyu gönder'}</button>
      </form>
      <section className="local-demo-answer" aria-labelledby="local-demo-answer-title" aria-live="polite">
        <div className="demo-section-heading"><div><span className="section-kicker">LOCAL MODEL RESPONSE</span><h2 id="local-demo-answer-title">Yanıt</h2></div>{response?.status === 'answered' && <span className="local-demo-origin">AI · yerel</span>}</div>
        {!response && !pending && !requestError && <div className="local-demo-placeholder"><span aria-hidden="true">↳</span><p>Model hazır olduğunda yanıt ve kaynak atıfları burada görünür.</p></div>}
        {pending && <div className="local-demo-placeholder" role="status"><span className="loading-orbit"/><p>Yerel model yanıtı hazırlanıyor…</p></div>}
        {requestError && <div className="local-demo-answer-error" role="alert"><p>{requestError}</p>{retryAllowed && <button className="subtle-button" type="button" disabled={pending || !question.trim()} onClick={() => void ask(question.trim())}>Yanıtı yeniden dene</button>}</div>}
        {response?.status === 'answered' && response.origin === 'ai' && <Answer response={response} meta={meta}/>}
        {response?.status === 'no_evidence' && <div className="local-demo-answer-state" role="status"><strong>Kaynakta kanıt bulunamadı</strong><p>Bu soru için dayanaklı yanıt üretilmedi. Yeni bir kod sorusu deneyebilirsiniz.</p></div>}
        {response?.status === 'unavailable' && <div className="local-demo-answer-error" role="status"><strong>Yerel model kullanılamıyor</strong><p>Bu istek için yanıt üretilmedi.</p><button className="subtle-button" type="button" onClick={() => setMetaAttempt((value) => value + 1)}>Model durumunu yenile</button><button className="subtle-button" type="button" disabled={!question.trim() || meta?.model_status !== 'ready'} onClick={() => void ask(question.trim())}>Soruyu tekrar dene</button></div>}
        {response?.status === 'rejected' && <div className="local-demo-answer-state" role="status"><strong>Soru işlenemedi</strong>{response.answer && <p className="local-demo-answer-text">{response.answer}</p>}</div>}
      </section>
    </div>
    <section className="local-demo-training" id="training-result"><div><span className="section-kicker">TRAINING EXPERIMENT</span><h2>Yerel QLoRA denemesi</h2><p>CUDA üzerinde kısa QLoRA smoke koşusu çalıştı. Bu çalışma yanıt kalitesinde iyileşme kanıtlamıyor; ayrı kalite değerlendirmesi yok.</p></div><span className="training-incomplete">TRAIN003 · incomplete</span><a href="#training-result">Eğitim deneyi sonucu <span aria-hidden="true">↗</span></a></section>
  </section>;
}

function Answer({ response, meta }: { response: LocalDemoResponse; meta: LocalDemoMeta | null }) {
  const validCitations = citationsForCommit(response, meta?.commit_sha ?? '');
  const sourceEntries = response.claims.flatMap((claim, claimIndex) => claim.citations
    .filter((citation) => validCitations.includes(citation)).map((citation) => ({ claim, citation, claimIndex })));
  return <div className="local-demo-answer-content"><p className="local-demo-answer-text">{response.answer}</p>
    {response.claims.map((claim, index) => <article className="local-demo-claim" key={`${index}:${claim.text}`}><p>{claim.text}</p>{claim.citations.filter((citation) => citation.commit_sha === response.commit_sha && citation.commit_sha === meta?.commit_sha).map((citation, citationIndex) => {
      const sourceIndex = sourceEntries.findIndex((entry) => entry.claimIndex === index && entry.citation === citation);
      return <a className="local-demo-citation-link" key={`${citation.path}:${citation.start_line}:${citationIndex}`} href={`#local-demo-source-${sourceIndex}`} aria-label={`Kaynağa git: ${citation.path}, satır ${citation.start_line}, SHA ${citation.commit_sha}`}>{citation.path}:{citation.start_line}{citation.end_line !== citation.start_line ? `–${citation.end_line}` : ''} · {citation.commit_sha.slice(0, 7)}</a>;
    })}</article>)}
    {response.claims.every((claim) => !claim.citations.some((citation) => citation.commit_sha === response.commit_sha && citation.commit_sha === meta?.commit_sha)) && <p className="local-demo-no-citations">Bu yanıt için geçerli kaynak atfı dönmedi. Yanıtın kaynak doğrulaması gösterilemiyor.</p>}
    {sourceEntries.length > 0 && <section className="local-demo-sources" aria-label="Source evidence"><h3>Kaynak kanıtı</h3>{sourceEntries.map(({ claim, citation }, index) => <article className="local-demo-source" id={`local-demo-source-${index}`} key={`${index}:${citation.path}:${citation.start_line}`}><a href="#local-demo-answer-title">{citation.path}:{citation.start_line}–{citation.end_line}</a><code>{citation.commit_sha}</code><pre>{citation.quote}</pre><p>İlişkili iddia: {claim.text}</p></article>)}</section>}
  </div>;
}
