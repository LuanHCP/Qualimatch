export type Status =
  | 'Aprovado'
  | 'Não conforme'
  | 'Restrito'
  | 'Cancelado'
  | 'Em análise'
  | 'Solicitado';
export type Category =
  | 'Misturas asfálticas'
  | 'Camadas cimentícias'
  | 'Agregados';
export type TraceHistory = { status: Status; date: string; owner: string };
export type Trace = {
  id: string;
  code: string;
  unit: string;
  company: string;
  contract: string;
  category: Category;
  material: string;
  place: string;
  status: Status;
  updated: string;
  owner: string;
  note?: string;
  history: TraceHistory[];
};
export type AppUser = {
  id: string;
  name: string;
  email: string;
  role: string;
  initials: string;
  // Controle de acesso por Sede: administradores enxergam e gerenciam todas
  // as Sedes; os demais usuários ficam restritos às Sedes listadas aqui.
  isAdmin?: boolean;
  sites?: string[];
  active?: boolean;
};

// Siglas de concessão para a codificação de cartas traço.
// Padrão de referência: PG.COR.GLO.QUA.001 (não incluso neste protótipo) —
// os exemplos do PE.COR.GLO.QUA.003 confirmam RSP, SOR e PTN; as demais
// siglas abaixo são uma estimativa e podem ser ajustadas livremente.
export const unitCodes: Record<string, string> = {
  AutoBan: 'ATB',
  MinasSP: 'MSP',
  Pantanal: 'PTN',
  PRVias: 'PRV',
  RioSP: 'RSP',
  RodoAnel: 'RAN',
  RodoNorte: 'RNT',
  Sorocabana: 'SOR',
  SPVias: 'SPV',
  ViaCosteira: 'VCT',
  ViaLagos: 'VLG',
  ViaOeste: 'VOE',
  ViaRio: 'VRI',
  ViaSul: 'VSU',
};

function codeSlug(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toUpperCase()
    .replace(/\s+/g, ' ');
}

function todayCompact(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

/**
 * Monta o código da carta traço / projeto de dosagem seguindo o item 7
 * (CODIFICAÇÃO) do PE.COR.GLO.QUA.003.
 *
 * 7.1 Concreto/argamassa/calda:
 *   [SEQ]-[MATERIAL]-[CONCESSÃO]-[CONSTRUTORA]-[USINA]-[fck]-[A/C]-[DATA]_[REV]
 * 7.2 Projeto de dosagem — misturas asfálticas:
 *   [SEQ]-[CONCESSÃO]-[CONSTRUTORA]-[USINA]-[TIPO DE CAP]-[%CAP]-[FORNECEDOR DO CAP]-[FAIXA]-[%RAP]-[DATA]_[REV]
 * 7.2 BGTC/BGMC:
 *   [SEQ]-[CONCESSÃO]-[CONSTRUTORA]-[USINA]-[TEOR DE CIMENTO]-[FAIXA]-[DATA]_[REV]
 *
 * "Agregados" (brita simples, macadame, rachão etc.) não tem codificação
 * prevista no procedimento — usamos um código simplificado nesse caso.
 */
export function buildTraceCode(params: {
  category: Category | '';
  sequential: number;
  unit: string;
  company: string;
  plant: string;
  capType?: string;
  capPercent?: string;
  capSupplier?: string;
  range?: string;
  rapPercent?: string;
  cementContent?: string;
  fck?: string;
  waterCement?: string;
  revision?: number;
  date?: Date;
}): string {
  const seq = String(Math.max(1, params.sequential)).padStart(3, '0');
  const concession = unitCodes[params.unit] || codeSlug(params.unit || '???').slice(0, 3);
  const builder = codeSlug(params.company || '???');
  const plant = codeSlug(params.plant || '???');
  const rev = String(params.revision ?? 0).padStart(2, '0');
  const dateRev = `${todayCompact(params.date)}_${rev}`;

  if (params.category === 'Misturas asfálticas') {
    return [
      seq,
      concession,
      builder,
      plant,
      codeSlug(params.capType || '???'),
      codeSlug(params.capPercent || '???'),
      codeSlug(params.capSupplier || '???'),
      codeSlug(params.range || '???'),
      codeSlug(params.rapPercent || '0%RAP'),
      dateRev,
    ].join('-');
  }
  if (params.category === 'Camadas cimentícias') {
    return [
      seq,
      concession,
      builder,
      plant,
      codeSlug(params.cementContent || '???'),
      codeSlug(params.range || '???'),
      dateRev,
    ].join('-');
  }
  if (params.category === 'Agregados') {
    // Não previsto no PE.COR.GLO.QUA.003 — código interno simplificado.
    return [seq, concession, builder, plant, codeSlug(params.range || 'AGR'), dateRev].join('-');
  }
  return [seq, concession, builder, plant, dateRev].join('-');
}

/** Item 9 — validade máxima de 12 meses a partir da data de conferência. */
export function traceValidUntil(approvedAt: Date): Date {
  const result = new Date(approvedAt);
  result.setMonth(result.getMonth() + 12);
  return result;
}

/** Dias corridos entre duas datas (para acompanhar o prazo do item 6). */
export function daysBetween(start: Date, end: Date): number {
  const ms = end.getTime() - start.getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
}

export const statuses: Status[] = [
  'Aprovado',
  'Não conforme',
  'Restrito',
  'Cancelado',
  'Em análise',
  'Solicitado',
];
export const units = [
  'AutoBan',
  'MinasSP',
  'Pantanal',
  'PRVias',
  'RioSP',
  'RodoAnel',
  'RodoNorte',
  'Sorocabana',
  'SPVias',
  'ViaCosteira',
  'ViaLagos',
  'ViaOeste',
  'ViaRio',
  'ViaSul',
];
export const categories: Category[] = [
  'Misturas asfálticas',
  'Camadas cimentícias',
  'Agregados',
];

// Opções abaixo transcritas do formulário oficial "Solicitação de Aprovação
// de Carta Traço" (Microsoft Forms) enviado pelo usuário. Vale conferir a
// lista de cimentos/fornecedores com o formulário original de tempos em
// tempos, pois é uma lista longa e sujeita a atualização pelos fabricantes.
export const usinaTypes = ['Volumétrica', 'Gravimétrica', 'Móvel'];
export const capDistributors = [
  'Stratura',
  'CBAA',
  'Betunel',
  'Disbral',
  'GRECA',
  'CBB',
  'EMAM',
  'NTA',
  'Outra',
];
export const cementSuppliers = [
  'CP I-32-Holcim',
  'CP I-40-Mizu',
  'CP II-E-32-CSN',
  'CP II-F-32-CSN',
  'CP II-E-40-CSN',
  'CP II-F-32-Votorantim',
  'CP II-F-40-Votorantim',
  'CP II-F-40-RS-Votorantim',
  'CP II-Z-32-RS-Votorantim',
  'CP II-F-32-Holcim',
  'CP II-E-32-Holcim',
  'CP II-F-32-Itambé',
  'CP II-32-Apodi',
  'CP II-E-32-RS-Cimento Nacional',
  'CP II-F-32-Tupi',
  'CP II-E-32-Tupi',
  'CP II-Z-32-Elizabeth',
  'CP II-Z-32-Ciplan',
  'CP II-F-32-InterCement',
  'CP II-F-32-Mizu',
  'CP II-E-32-Votorantim',
  'CP II-E-32-InterCement',
  'CP II-Z-32-Votorantim',
  'CP II-Z-32-CSN',
  'CP II-E-40-Votorantim',
  'CP II-E-40-InterCement',
  'CP II-E-40-Tupi',
  'CP II-40-RS-Tupi',
  'CP II-Z-40-Votorantim',
  'CP III-32-RS-CSN',
  'CP III-40-RS-CSN',
  'CP III-40-RS-Holcim',
  'CP III-40-RS-Apodi',
  'CP III-40-RS-Cimento Nacional',
  'CP III-E-32-BC-Votorantim',
  'CP III-E-32-BC-CSN',
  'CP III-E-40-RS, BC-Votorantim',
  'CP III-E-40-RS, BC-CSN',
  'CP III-40-RS-Mizu',
  'CP III-E-40-CSN',
  'CP IV-32-RS-Votorantim',
  'CP IV-32-RS-Itambé',
  'CP IV-32-RS-Apodi',
  'CP IV-32-RS-Cimento Nacional',
  'CP IV-Z-32-RS, BC-Votorantim',
  'CP IV-Z-32-RS, BC-Cimento Nacional',
  'CP V-40-ARI-Votorantim',
  'CP V-RS-NACIONAL',
  'CP V-40-ARI-Itambé',
  'CP III-40-RS-VOTORAN',
  'CP V-40-ARI-Apodi',
  'CP V-40-ARI, RS-Mizu',
  'CP V-ARI-Nacional',
  'CP V-ARI-Votorantim',
  'CP V-ARI-InterCement',
  'CP V-ARI-CSN',
  'CP V-ARI, RS-Votorantim',
  'CP V-ARI, RS-InterCement',
  'CP V-ARI, RS-CSN',
  'CPB-Branco-Votorantim',
  'CP III-RS-VOTORAN',
  'Outra',
];
export const materials: Record<Category, string[]> = {
  'Misturas asfálticas': [
    'CBUQ',
    'PMQ',
    'SMA',
    'PMF',
    'MRAF',
    'Lama asfáltica',
    'TS (TSS/TSD/TST)',
    'CPA',
    'Gap Graded',
    'Base Negra',
    'Reciclagem de pavimento',
  ],
  'Camadas cimentícias': [
    'Brita graduada melhorada com cimento',
    'Brita graduada tratada com cimento',
  ],
  Agregados: ['Brita graduada simples', 'Macadame', 'Rachão', 'Pedra britada'],
};
export const statusMeta: Record<Status, { className: string; short: string }> =
  {
    Aprovado: { className: 'approved', short: 'AP' },
    'Não conforme': { className: 'nonconforming', short: 'NC' },
    Restrito: { className: 'restricted', short: 'RE' },
    Cancelado: { className: 'cancelled', short: 'CA' },
    'Em análise': { className: 'analysis', short: 'EA' },
    Solicitado: { className: 'requested', short: 'SO' },
  };
// Selos reais recebidos do usuário (recortados do PDF enviado). Só existem
// para 3 status até agora — os demais continuam usando o ícone genérico de
// escudo até o usuário enviar os selos correspondentes.
export const statusSeals: Partial<Record<Status, string>> = {
  Aprovado: '/selos/conforme.png',
  'Não conforme': '/selos/nao-conforme.png',
  Restrito: '/selos/restrito.png',
};
export const initialUsers: AppUser[] = [
  {
    id: 'u1',
    name: 'Carolina Mendes',
    email: 'carolina.mendes@qualimatch.local',
    role: 'Analista de Qualidade',
    initials: 'CM',
    isAdmin: false,
    sites: ['PRVias'],
    active: true,
  },
  {
    id: 'u2',
    name: 'Marcos Vieira',
    email: 'marcos.vieira@qualimatch.local',
    role: 'Coordenador Técnico',
    initials: 'MV',
    isAdmin: false,
    sites: ['SPVias', 'MinasSP'],
    active: true,
  },
  {
    id: 'u3',
    name: 'Juliana Costa',
    email: 'juliana.costa@qualimatch.local',
    role: 'Analista de Laboratório',
    initials: 'JC',
    isAdmin: false,
    sites: ['AutoBan'],
    active: true,
  },
  {
    id: 'u4',
    name: 'Fábio Rocha',
    email: 'fabio.rocha@qualimatch.local',
    role: 'Engenheiro de Pavimentos',
    initials: 'FR',
    isAdmin: false,
    sites: ['RodoAnel'],
    active: true,
  },
];
const baseTraces: Trace[] = [
  {
    id: '1',
    code: '001-ATB-HORIZONTE-POLIMIX-CAP 50/70-5,2%-CBB-C-0%RAP-20260828_00',
    unit: 'AutoBan',
    company: 'Construtora Horizonte',
    contract: 'CT-184/26',
    category: 'Misturas asfálticas',
    material: 'CBUQ',
    place: 'Km 88+500 · Pista Norte',
    status: 'Em análise',
    updated: 'Hoje, 10:42',
    owner: 'Carolina Mendes',
    history: [
      {
        status: 'Solicitado',
        date: '28/08/2026 · 09:14',
        owner: 'Rafael Lima',
      },
      { status: 'Em análise', date: 'Hoje · 10:42', owner: 'Carolina Mendes' },
    ],
  },
  {
    id: '2',
    code: '002-VOE-TERRAPLENO-PSI-3%-FAIXA 2-20260825_00',
    unit: 'ViaOeste',
    company: 'Terrapleno Engenharia',
    contract: 'CT-166/26',
    category: 'Camadas cimentícias',
    material: 'BGTC',
    place: 'Lote 03 · Marginal Leste',
    status: 'Aprovado',
    updated: '01/09/2026',
    owner: 'Marcos Vieira',
    history: [
      { status: 'Solicitado', date: '25/08/2026 · 15:30', owner: 'Ana Paula' },
      {
        status: 'Aprovado',
        date: '01/09/2026 · 16:18',
        owner: 'Marcos Vieira',
      },
    ],
  },
  {
    id: '3',
    code: '003-SPV-PAVITERRA-PEDREIRA SPV-FAIXA A-20260822_00',
    unit: 'SPVias',
    company: 'Paviterra',
    contract: 'CT-159/26',
    category: 'Agregados',
    material: 'Brita graduada simples',
    place: 'Km 231 · Base',
    status: 'Não conforme',
    updated: '31/08/2026',
    owner: 'Juliana Costa',
    note: 'Ajustar curva granulométrica e reenviar o laudo.',
    history: [
      { status: 'Solicitado', date: '22/08/2026 · 08:40', owner: 'Paulo Reis' },
      {
        status: 'Não conforme',
        date: '31/08/2026 · 14:27',
        owner: 'Juliana Costa',
      },
    ],
  },
  {
    id: '4',
    code: '004-RSP-NOVAVIA-POLIMIX-CAP 60/85-6,0%-CBB-B-0%RAP-20260818_00',
    unit: 'RioSP',
    company: 'Nova Via Infra',
    contract: 'CT-142/26',
    category: 'Misturas asfálticas',
    material: 'SMA',
    place: 'Km 17+200 · Faixa 2',
    status: 'Restrito',
    updated: '29/08/2026',
    owner: 'Carolina Mendes',
    note: 'Uso restrito ao trecho experimental de 500 m.',
    history: [
      {
        status: 'Solicitado',
        date: '18/08/2026 · 13:02',
        owner: 'Ricardo Alves',
      },
      {
        status: 'Restrito',
        date: '29/08/2026 · 09:50',
        owner: 'Carolina Mendes',
      },
    ],
  },
  {
    id: '5',
    code: '005-SOR-EIXO OBRAS-PEDREIRA SOR-MACADAME-20260815_00',
    unit: 'Sorocabana',
    company: 'Eixo Obras',
    contract: 'CT-139/26',
    category: 'Agregados',
    material: 'Macadame',
    place: 'Acesso operacional 04',
    status: 'Solicitado',
    updated: '15/08/2026',
    owner: '—',
    history: [
      {
        status: 'Solicitado',
        date: '15/08/2026 · 17:22',
        owner: 'Beatriz Nunes',
      },
    ],
  },
  {
    id: '6',
    code: '006-RNT-VIA FORTE-PAVFLEX-CAP 50/70-5,5%-CBB-PMQ-0%RAP-20260807_00',
    unit: 'RodoNorte',
    company: 'Via Forte',
    contract: 'CT-121/26',
    category: 'Misturas asfálticas',
    material: 'PMQ',
    place: 'Km 42+800 · Acostamento',
    status: 'Cancelado',
    updated: '20/08/2026',
    owner: 'Fábio Rocha',
    note: 'Substituído pelo traço TR-2026-068.',
    history: [
      {
        status: 'Solicitado',
        date: '07/08/2026 · 10:18',
        owner: 'Luiza Prado',
      },
      { status: 'Cancelado', date: '20/08/2026 · 12:11', owner: 'Fábio Rocha' },
    ],
  },
];

// A edição pública usa exatamente 200 registros fictícios também quando o
// PostgreSQL ainda não foi configurado. Assim o módulo incorporado continua
// demonstrável logo após o clone, sem recorrer a dados ou caminhos reais.
export const initialTraces: Trace[] = Array.from({ length: 200 }, (_, index) => {
  const n = index + 1;
  const template = baseTraces[index % baseTraces.length];
  const status = statuses[index % statuses.length];
  const category = categories[index % categories.length];
  const material = materials[category][index % materials[category].length];
  return {
    ...template,
    id: `demo-${String(n).padStart(4, '0')}`,
    code: `TR-DEMO-${String(n).padStart(4, '0')}`,
    unit: units[index % units.length],
    company: ['Construtora Alfa', 'Construtora Beta', 'Engenharia Gama'][index % 3],
    contract: `CT-DEMO-${String(1 + (index % 8)).padStart(2, '0')}`,
    category,
    material,
    place: `Trecho fictício ${1 + (index % 20)} · km ${80 + (index % 120)}+000`,
    status,
    updated: `${String(1 + (index % 28)).padStart(2, '0')}/10/2026`,
    owner: 'Equipe Demonstração',
    note: 'Registro inteiramente fictício, criado para demonstração.',
    history: [{ status, date: `${String(1 + (index % 28)).padStart(2, '0')}/10/2026`, owner: 'Equipe Demonstração' }],
  };
});
