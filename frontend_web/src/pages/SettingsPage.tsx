import { useQuery } from "@tanstack/react-query";
import { Database, LockKeyhole, Palette, UserRound, Cpu, Bell, Brain, ShieldCheck, SlidersHorizontal, LineChart, UserCog } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { DataStatusBadge } from "../components/ui/DataBadges";
import { useAuth } from "../features/auth/useAuth";
import { defaultVisualPreferences, readVisualPreferences, saveVisualPreferences, type VisualPreferences } from "../features/preferences/visualPreferences";
import { endpoints } from "../services/endpoints/data";
import { investorProfileEndpoints } from "../services/endpoints/investorProfile";
import { formatDateTimeBR } from "../utils/formatters";

const sections = [
  ["conta", "Conta e Perfil", UserRound], ["perfil-investidor", "Perfil do Investidor", UserCog], ["aparencia", "Aparência", Palette], ["mercado", "Mercado e Dados", LineChart],
  ["fontes", "Fontes de Dados", Database], ["diagnostico", "Diagnóstico de Dados", ShieldCheck], ["carteira", "Carteira e Análise", SlidersHorizontal],
  ["ia", "Inteligência Artificial", Brain], ["notificacoes", "Notificações", Bell], ["privacidade", "Privacidade e Segurança", LockKeyhole], ["avancado", "Avançado", Cpu],
] as const;

const ONBOARDING_STATUS_LABELS: Record<string, string> = {
  needs_onboarding: "Onboarding não iniciado",
  in_progress: "Onboarding em andamento",
  pending_confirmation: "Aguardando sua confirmação",
  complete: "Concluído",
  needs_review: "Revisão recomendada",
};

export function SettingsPage() {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(readVisualPreferences);
  const capabilities = useQuery({ queryKey: ["provider-capabilities", token], queryFn: () => endpoints.providerCapabilities(token!), enabled: Boolean(token) });
  const investorProfile = useQuery({ queryKey: ["investor-profile", token], queryFn: () => investorProfileEndpoints.get(token!), enabled: Boolean(token) });
  const update = (next: VisualPreferences) => { setPrefs(next); saveVisualPreferences(next); };

  async function reviewProfile() {
    if (!token) return;
    if (investorProfile.data && ["complete", "needs_review"].includes(investorProfile.data.status)) {
      await investorProfileEndpoints.review(token);
    }
    navigate("/onboarding");
  }
  return <div className="settings-workstation">
    <aside className="settings-index" aria-label="Categorias de configurações">{sections.map(([id,label,Icon]) => <a key={id} href={`#${id}`}><Icon size={17}/><span>{label}</span></a>)}</aside>
    <div className="page-stack settings-content">
      <section className="page-heading"><h2>Configurações</h2><p>Preferências locais e capacidades reais, separadas de recursos planejados.</p></section>
      <SettingsSection id="conta" title="Conta e Perfil" state="Real"><dl className="settings-facts"><div><dt>Nome</dt><dd>{user?.name}</dd></div><div><dt>E-mail</dt><dd>{user?.email}</dd></div><div><dt>Conta criada</dt><dd>{formatDateTimeBR(user?.created_at)}</dd></div></dl><Link to="/esqueci-minha-senha">Acessar recuperação de senha</Link></SettingsSection>
      <SettingsSection id="perfil-investidor" title="Perfil do Investidor" state="Real">
        {investorProfile.isLoading ? <p>Consultando seu perfil…</p> : investorProfile.error ? <p className="error-text">Não foi possível consultar seu perfil.</p> : <>
          <dl className="settings-facts">
            <div><dt>Status</dt><dd>{ONBOARDING_STATUS_LABELS[investorProfile.data?.status ?? ""] ?? "Não informado"}</dd></div>
            <div><dt>Classificação</dt><dd>{investorProfile.data?.dimensions?.overall_classification ?? "Ainda não calculada"}</dd></div>
            <div><dt>Objetivo</dt><dd>{investorProfile.data?.primary_objective ?? "Não informado"}</dd></div>
            <div><dt>Última revisão</dt><dd>{formatDateTimeBR(investorProfile.data?.last_reviewed_at ?? investorProfile.data?.confirmed_at ?? undefined)}</dd></div>
          </dl>
          <button className="button button-secondary" type="button" onClick={reviewProfile}>
            {investorProfile.data?.status === "complete" ? "Refazer avaliação" : "Continuar onboarding"}
          </button>
        </>}
      </SettingsSection>
      <SettingsSection id="aparencia" title="Aparência" state="Local"><div className="settings-controls"><label>Perfil visual<select value={prefs.profile} onChange={e=>update({...prefs,profile:e.target.value as VisualPreferences["profile"]})}><option value="compact">Compacto</option><option value="analytical">Analítico</option><option value="workstation">Workstation</option></select></label><label>Transparência<select value={prefs.transparency} onChange={e=>update({...prefs,transparency:e.target.value as VisualPreferences["transparency"]})}><option value="standard">Padrão</option><option value="reduced">Reduzida</option></select></label><label>Tamanho da fonte<select value={prefs.fontScale} onChange={e=>update({...prefs,fontScale:e.target.value as VisualPreferences["fontScale"]})}><option value="standard">Padrão</option><option value="large">Ampliada</option></select></label><label className="check-setting"><input type="checkbox" checked={prefs.reducedMotion} onChange={e=>update({...prefs,reducedMotion:e.target.checked})}/> Reduzir movimento</label><button className="button button-secondary" type="button" onClick={()=>update(defaultVisualPreferences)}>Restaurar preferências visuais</button></div></SettingsSection>
      <SettingsSection id="mercado" title="Mercado e Dados" state="Real"><p>As telas usam dados fornecidos pela FastAPI e identificam resultados parciais ou indisponíveis.</p><DataStatusBadge status={capabilities.data?.reachable === true ? "live" : capabilities.data?.reachable === false ? "unavailable" : "partial"}/></SettingsSection>
      <SettingsSection id="fontes" title="Fontes de Dados" state="Real">{capabilities.isLoading?<p>Consultando capacidades…</p>:capabilities.error?<p className="error-text">Não foi possível consultar as capacidades.</p>:<><dl className="settings-facts"><div><dt>Provedor</dt><dd>{capabilities.data?.provider}</dd></div><div><dt>Configurado</dt><dd>{capabilities.data?.configured?"Sim":"Não"}</dd></div><div><dt>Acessível</dt><dd>{capabilities.data?.reachable==null?"Não monitorado":capabilities.data.reachable?"Sim":"Não"}</dd></div><div><dt>Última verificação</dt><dd>{formatDateTimeBR(capabilities.data?.last_checked_at)}</dd></div></dl><DomainList title="Domínios suportados" values={capabilities.data?.supported_domains}/><DomainList title="Domínios acessíveis" values={capabilities.data?.accessible_domains}/><DomainList title="Domínios restritos" values={capabilities.data?.restricted_domains}/></>}</SettingsSection>
      <SettingsSection id="diagnostico" title="Diagnóstico de Dados" state="Real"><p>Indicadores encontrados, ausentes, freshness e procedência aparecem nos detalhes de Mercado e Planejar quando retornados pela API.</p><ol className="fallback-chain"><li>Snapshot válido</li><li>BRAPI acessível</li><li>Fonte oficial</li><li>Indicador manual</li><li>Indisponível</li></ol><small>Política configurada de resolução; não representa fontes consultadas nesta sessão.</small></SettingsSection>
      <SettingsSection id="carteira" title="Carteira e Análise" state="Real"><p>Política do investidor, limites e alocação são administrados em Planejar.</p><Link to="/planejar">Abrir Planejar</Link></SettingsSection>
      <SettingsSection id="ia" title="Inteligência Artificial" state="Real"><p>A Mesa IA usa o contrato V1, somente leitura. Chaves, modelo interno e segredos não são expostos.</p><Planned text="Memória persistente e autonomia de agentes"/></SettingsSection>
      <SettingsSection id="notificacoes" title="Notificações" state="Planejado"><Planned text="Canais e preferências de notificação"/></SettingsSection>
      <SettingsSection id="privacidade" title="Privacidade e Segurança" state="Real"><p>Autenticação Bearer e fluxos reais de senha permanecem centralizados.</p><Planned text="Exportação de dados e gestão de sessões"/></SettingsSection>
      <SettingsSection id="avancado" title="Avançado" state="Planejado"><p>Versão pública: frontend Quantum Prism.</p><Planned text="Logs locais e modo desenvolvedor"/></SettingsSection>
    </div>
  </div>;
}
function SettingsSection({id,title,state,children}:{id:string;title:string;state:"Real"|"Local"|"Planejado";children:React.ReactNode}){return <Card className="settings-section"><div id={id} className="settings-anchor"/><header><h2>{title}</h2><span className={`setting-kind kind-${state.toLowerCase()}`}>{state}</span></header>{children}</Card>}
function Planned({text}:{text:string}){return <div className="planned-control"><span>Planejado</span><p>{text}</p><button type="button" disabled>Recurso futuro</button></div>}
function DomainList({title,values}:{title:string;values?:string[]}){return <div className="domain-list"><strong>{title}</strong><p>{values?.length?values.join(" · "):"Não informado pelo provedor"}</p></div>}
