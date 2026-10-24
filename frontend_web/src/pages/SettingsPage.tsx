import { useQuery } from "@tanstack/react-query";
import { Bell, Brain, LockKeyhole, LogOut, Palette, UserCog, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { useAuth } from "../features/auth/useAuth";
import {
  continueOrReviewInvestorProfile,
  investorProfileActionLabel,
  investorProfileObjectiveLabel,
  investorProfileRiskLabel,
  investorProfileStatusLabel,
} from "../features/investorProfile/presentation";
import { defaultVisualPreferences, readVisualPreferences, saveVisualPreferences, type VisualPreferences } from "../features/preferences/visualPreferences";
import { investorProfileEndpoints } from "../services/endpoints/investorProfile";
import { formatDateTimeBR } from "../utils/formatters";

// Estrutura voltada ao usuário final (Correção interface, seção 21):
// nunca mais uma página de administração técnica. Seções técnicas
// removidas da UI comum -- Mercado e Dados, Fontes de Dados, Diagnóstico
// de Dados -- consultavam somente `endpoints.providerCapabilities`
// (GET /market/provider-capabilities), que não é usado em nenhum outro
// lugar do frontend (confirmado na auditoria); o endpoint, o schema e o
// serviço de backend continuam intactos, só deixam de ser consultados/
// exibidos aqui.
const sections = [
  ["conta", "Conta e Perfil", UserRound],
  ["perfil-investidor", "Perfil do Investidor", UserCog],
  ["aparencia", "Interface e Aparência", Palette],
  ["notificacoes", "Notificações", Bell],
  ["privacidade", "Privacidade e Segurança", LockKeyhole],
  ["ia", "Mesa IA", Brain],
  ["sair", "Sair da conta", LogOut],
] as const;

export function SettingsPage() {
  const { token, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [prefs, setPrefs] = useState(readVisualPreferences);
  const investorProfile = useQuery({ queryKey: ["investor-profile", token], queryFn: () => investorProfileEndpoints.get(token!), enabled: Boolean(token) });
  const update = (next: VisualPreferences) => { setPrefs(next); saveVisualPreferences(next); };

  // Deep link #conta (Correção interface, seção 20): React Router v6 não
  // rola automaticamente para um fragmento de hash em navegação client-
  // side sem <ScrollRestoration> (data router, não usado neste app) ou um
  // efeito manual -- nunca dependeu de comportamento incidental do
  // navegador, implementado aqui de forma simples, sem biblioteca externa.
  useEffect(() => {
    if (!location.hash) return;
    const id = location.hash.slice(1);
    const target = document.getElementById(id);
    target?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [location.hash]);

  async function reviewProfile() {
    if (!token) return;
    await continueOrReviewInvestorProfile(token, investorProfile.data?.status, navigate);
  }

  return <div className="settings-workstation">
    <aside className="settings-index" aria-label="Categorias de configurações">{sections.map(([id,label,Icon]) => <a key={id} href={`#${id}`}><Icon size={17}/><span>{label}</span></a>)}</aside>
    <div className="page-stack settings-content">
      <section className="page-heading"><h2>Configurações</h2><p>Preferências da sua conta e da experiência Mesa Quant Master.</p></section>
      <SettingsSection id="conta" title="Conta e Perfil" state="Real">
        <dl className="settings-facts"><div><dt>Nome</dt><dd>{user?.name}</dd></div><div><dt>E-mail</dt><dd>{user?.email}</dd></div><div><dt>Conta criada</dt><dd>{formatDateTimeBR(user?.created_at)}</dd></div></dl>
        <Link to="/esqueci-minha-senha">Acessar recuperação de senha</Link>
      </SettingsSection>
      <SettingsSection id="perfil-investidor" title="Perfil do Investidor" state="Real">
        {investorProfile.isLoading ? <p>Consultando seu perfil…</p> : investorProfile.error ? <p className="error-text">Não foi possível consultar seu perfil.</p> : <>
          <dl className="settings-facts">
            <div><dt>Status</dt><dd>{investorProfileStatusLabel(investorProfile.data?.status)}</dd></div>
            <div><dt>Classificação</dt><dd>{investorProfile.data?.dimensions?.overall_classification ? investorProfileRiskLabel(investorProfile.data.dimensions.overall_classification) : "Ainda não calculada"}</dd></div>
            <div><dt>Objetivo</dt><dd>{investorProfileObjectiveLabel(investorProfile.data?.primary_objective)}</dd></div>
            <div><dt>Última revisão</dt><dd>{formatDateTimeBR(investorProfile.data?.last_reviewed_at ?? investorProfile.data?.confirmed_at ?? undefined)}</dd></div>
          </dl>
          <button className="button button-secondary" type="button" onClick={reviewProfile}>
            {investorProfileActionLabel(investorProfile.data?.status)}
          </button>
        </>}
        <p className="helper"><Link to="/planejar">Abrir Planejar</Link> para estratégia, alocação e montagem de carteira.</p>
      </SettingsSection>
      <SettingsSection id="aparencia" title="Interface e Aparência" state="Local">
        <div className="settings-controls">
          <label>Perfil visual
            <select value={prefs.profile} onChange={e=>update({...prefs,profile:e.target.value as VisualPreferences["profile"]})}>
              <option value="compact">Compacto</option>
              <option value="workstation">Workstation</option>
            </select>
          </label>
          <label>Transparência<select value={prefs.transparency} onChange={e=>update({...prefs,transparency:e.target.value as VisualPreferences["transparency"]})}><option value="standard">Padrão</option><option value="reduced">Reduzida</option></select></label>
          <label>Tamanho da fonte<select value={prefs.fontScale} onChange={e=>update({...prefs,fontScale:e.target.value as VisualPreferences["fontScale"]})}><option value="standard">Padrão</option><option value="large">Ampliada</option></select></label>
          <label className="check-setting"><input type="checkbox" checked={prefs.reducedMotion} onChange={e=>update({...prefs,reducedMotion:e.target.checked})}/> Reduzir movimento</label>
          <button className="button button-secondary" type="button" onClick={()=>update(defaultVisualPreferences)}>Restaurar preferências visuais</button>
        </div>
      </SettingsSection>
      <SettingsSection id="notificacoes" title="Notificações" state="Planejado">
        <p>As preferências de notificações ainda não estão disponíveis nesta versão.</p>
      </SettingsSection>
      <SettingsSection id="privacidade" title="Privacidade e Segurança" state="Real">
        <p>A recuperação e alteração de senha ficam disponíveis em Conta e Perfil.</p>
        <p className="helper">Exportação de dados e gestão de sessões ainda não estão disponíveis nesta versão.</p>
      </SettingsSection>
      <SettingsSection id="ia" title="Mesa IA" state="Real">
        <p>Mesa IA — pausada. Nenhuma chamada externa é realizada.</p>
        <p className="helper">Conversa e envio de dados não estão disponíveis nesta interface.</p>
      </SettingsSection>
      <SettingsSection id="sair" title="Sair da conta" state="Real">
        <p className="helper">Encerra sua sessão neste dispositivo.</p>
        <button className="button button-secondary" type="button" onClick={logout}>Sair da conta</button>
      </SettingsSection>
    </div>
  </div>;
}
function SettingsSection({id,title,state,children}:{id:string;title:string;state:"Real"|"Local"|"Planejado";children:React.ReactNode}){return <Card className="settings-section"><div id={id} className="settings-anchor"/><header><h2>{title}</h2><span className={`setting-kind kind-${state.toLowerCase()}`}>{state}</span></header>{children}</Card>}
