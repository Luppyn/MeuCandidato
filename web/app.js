/*
 * MeuCandidato - interface de consulta.
 *
 * JavaScript puro, sem framework e sem etapa de build: o arquivo que roda no
 * navegador e exatamente este, o que permite auditar a interface do mesmo jeito
 * que se audita o backend.
 */
'use strict';

const estado = {
  colunas: [],
  fontes: {},
  links: {},
  opcoes: null,
  filtros: {},
  pagina: 1,
  limite: 100,
  ordem: 'nm_urna',
  direcao: 'asc',
  mostrarPesadas: false,
  ultimoResultado: null,
};

const $ = (sel) => document.querySelector(sel);
const criar = (tag, props = {}, filhos = []) => {
  const el = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === 'texto') el.textContent = v;
    else if (k === 'classe') el.className = v;
    else if (v !== null && v !== undefined) el.setAttribute(k, v);
  });
  (Array.isArray(filhos) ? filhos : [filhos]).forEach((f) => {
    if (f) el.append(f);
  });
  return el;
};

// Cargos municipais: exigem escolher municipio, e nao so a UF.
const CARGOS_MUNICIPAIS = [11, 12, 13];

/* -------------------------------------------------------------------- rede */

async function pegar(caminho) {
  const resposta = await fetch(caminho, { headers: { Accept: 'application/json' } });
  const dados = await resposta.json().catch(() => ({ erro: 'resposta invalida do servidor' }));
  if (!resposta.ok) throw new Error(dados.erro || `erro ${resposta.status}`);
  return dados;
}

/*
 * O site roda de dois jeitos, com a mesma interface:
 *
 *   api       servidor.py servindo o SQLite — uso local, filtro no servidor
 *   estatico  arquivos JSON pré-gerados — hospedagem sem servidor, filtro
 *             no navegador dentro do recorte já baixado
 *
 * A detecção é por tentativa: se /api/saude responde, é o servidor. Em
 * hospedagem estática essa rota devolve 404 e o modo cai para estático.
 */

const fonte = {
  modo: null,
  meta: null,
  recortes: [],
  cacheGrade: new Map(),
  cacheBens: new Map(),

  async detectar() {
    try {
      const r = await fetch('api/saude', { headers: { Accept: 'application/json' } });
      if (r.ok) { this.modo = 'api'; return; }
    } catch (e) { /* sem servidor: modo estático */ }
    this.modo = 'estatico';
    this.meta = await pegar('dados/meta.json');
  },

  configuracao() {
    return this.modo === 'api'
      ? Promise.all([pegar('api/colunas'), pegar('api/fontes'),
                     pegar('api/procedencia'), pegar('api/opcoes')])
      : Promise.all([pegar('dados/colunas.json'), pegar('dados/fontes.json'),
                     pegar('dados/procedencia.json'), pegar('dados/opcoes.json')]);
  },

  /** Nome do arquivo de recorte para os filtros atuais. */
  arquivoDoRecorte(filtros) {
    const municipal = CARGOS_MUNICIPAIS.includes(Number(filtros.cargo));
    const partes = [filtros.ano, filtros.cargo, filtros.uf];
    if (municipal && filtros.ue) partes.push(filtros.ue);
    return partes.join('-');
  },

  async grade(filtros) {
    const nome = this.arquivoDoRecorte(filtros);
    if (!this.cacheGrade.has(nome)) {
      this.cacheGrade.set(nome, await pegar(`dados/grade/${nome}.json`));
    }
    return this.cacheGrade.get(nome);
  },

  async bens(filtros) {
    const nome = this.arquivoDoRecorte(filtros);
    if (!this.cacheBens.has(nome)) {
      this.cacheBens.set(nome, await pegar(`dados/bens/${nome}.json`));
    }
    return this.cacheBens.get(nome);
  },

  /** Aplica nome, partido, situação, ordenação e paginação no navegador. */
  filtrarLocalmente(candidatos, filtros, { ordem, direcao, pagina, limite }) {
    const semAcento = (s) => (s || '')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();

    let linhas = candidatos;
    if (filtros.ue) linhas = linhas.filter((c) => c.sg_ue === filtros.ue);
    if (filtros.partido) {
      linhas = linhas.filter((c) => c.sg_partido === filtros.partido
                                 || c.nr_partido === filtros.partido);
    }
    if (filtros.situacao) {
      linhas = linhas.filter((c) => c.ds_situacao_candidatura === filtros.situacao);
    }
    if (filtros.nome) {
      const alvo = semAcento(filtros.nome);
      linhas = linhas.filter((c) => semAcento(
        [c.nm_candidato, c.nm_urna, c.nm_social].filter(Boolean).join(' ')).includes(alvo));
    }

    const sinal = direcao === 'desc' ? -1 : 1;
    linhas = [...linhas].sort((a, b) => {
      const x = a[ordem], y = b[ordem];
      if (x === y) return (a.nm_urna || '').localeCompare(b.nm_urna || '', 'pt-BR');
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * sinal;
      return String(x).localeCompare(String(y), 'pt-BR') * sinal;
    });

    const total = linhas.length;
    const paginas = Math.max(1, Math.ceil(total / limite));
    const inicio = (pagina - 1) * limite;
    return { total, pagina, limite, paginas, candidatos: linhas.slice(inicio, inicio + limite) };
  },
};

/* ---------------------------------------------------------------- formatos */

function formatarMoeda(valor) {
  if (valor === null || valor === undefined || valor === '') return '';
  const numero = Number(valor);
  if (Number.isNaN(numero)) return String(valor);
  return numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarNumero(valor) {
  if (valor === null || valor === undefined || valor === '') return '';
  const numero = Number(valor);
  return Number.isNaN(numero) ? String(valor) : numero.toLocaleString('pt-BR');
}

function formatarData(valor) {
  return valor || '';
}

function formatarDataHora(valor) {
  if (!valor) return '—';
  const data = new Date(valor);
  return Number.isNaN(data.getTime())
    ? valor
    : data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

/** Monta o link de conferencia manual da fonte para um candidato. */
function linkManual(slugFonte, candidato) {
  const fonte = estado.fontes[slugFonte];
  if (!fonte || !fonte.url_consulta_manual) return null;
  const nome = candidato.nm_candidato || candidato.nm_urna || '';
  return fonte.url_consulta_manual
    .replace('{nome_url}', encodeURIComponent(nome))
    .replace('{nome}', nome)
    .replace('{uf}', candidato.sg_uf || '')
    .replace('{cargo}', candidato.ds_cargo || '')
    .replace('{ano}', candidato.ano_eleicao || '');
}

/* --------------------------------------------------------------- filtros */

function preencherSelect(select, itens, { valor, rotulo, vazio }) {
  select.textContent = '';
  if (vazio !== undefined) select.append(criar('option', { value: '', texto: vazio }));
  itens.forEach((item) => {
    select.append(criar('option', {
      value: String(valor(item)),
      texto: rotulo(item),
    }));
  });
}

function atualizarCargosEUfs() {
  const ano = Number($('#f-ano').value);
  const opcoes = estado.opcoes;

  const cargos = [];
  const vistos = new Set();
  opcoes.cargos
    .filter((c) => c.ano === ano)
    .forEach((c) => {
      if (!vistos.has(c.codigo)) {
        vistos.add(c.codigo);
        cargos.push(c);
      }
    });

  const cargoAtual = $('#f-cargo').value;
  preencherSelect($('#f-cargo'), cargos, {
    valor: (c) => c.codigo,
    rotulo: (c) => c.nome,
    vazio: 'Selecione…',
  });
  if (cargos.some((c) => String(c.codigo) === cargoAtual)) $('#f-cargo').value = cargoAtual;

  atualizarUfs();
}

function atualizarUfs() {
  const ano = Number($('#f-ano').value);
  const cargo = Number($('#f-cargo').value);
  const ufs = [...new Set(
    estado.opcoes.ufs
      .filter((u) => u.ano === ano && (!cargo || u.cargo === cargo))
      .map((u) => u.sigla),
  )].sort();

  const ufAtual = $('#f-uf').value;
  preencherSelect($('#f-uf'), ufs, {
    valor: (u) => u,
    rotulo: (u) => u,
    vazio: 'Selecione…',
  });
  if (ufs.includes(ufAtual)) $('#f-uf').value = ufAtual;

  atualizarUnidades();
}

function atualizarUnidades() {
  const ano = Number($('#f-ano').value);
  const cargo = Number($('#f-cargo').value);
  const uf = $('#f-uf').value;
  const municipal = CARGOS_MUNICIPAIS.includes(cargo);

  $('#rotulo-ue').hidden = !municipal;
  if (!municipal) {
    $('#f-ue').value = '';
    return;
  }
  $('#rotulo-ue').querySelector('span').textContent = 'Município / unidade eleitoral *';

  const unidades = estado.opcoes.unidades
    .filter((u) => u.ano === ano && u.cargo === cargo && u.uf === uf)
    .sort((a, b) => String(a.nome).localeCompare(String(b.nome), 'pt-BR'));

  // Em cargo municipal o município é obrigatório: uma lista de vereadores de
  // um estado inteiro não é um recorte útil, e no modo estático cada município
  // é um arquivo próprio.
  preencherSelect($('#f-ue'), unidades, {
    valor: (u) => u.codigo,
    rotulo: (u) => u.nome || u.codigo,
    vazio: 'Selecione…',
  });
}

async function carregarBase() {
  await fonte.detectar();
  const [colunas, fontes, procedencia, opcoes] = await fonte.configuracao();
  fonte.recortes = opcoes.recortes || [];

  estado.colunas = colunas.colunas;
  estado.links = fontes.links || {};
  fontes.fontes.forEach((f) => { estado.fontes[f.slug] = f; });
  estado.opcoes = opcoes;
  estado.procedencia = procedencia;

  if (procedencia.origem_base === 'EXEMPLO') {
    const aviso = $('#aviso-base');
    aviso.hidden = false;
    aviso.textContent = procedencia.aviso_base
      || 'Base de demonstração com dados fictícios.';
  }

  preencherSelect($('#f-ano'), opcoes.anos, { valor: (a) => a, rotulo: (a) => a });
  preencherSelect($('#f-partido'), opcoes.partidos, {
    valor: (p) => p.sigla,
    rotulo: (p) => (p.nome ? `${p.sigla} — ${p.nome}` : p.sigla),
    vazio: 'Todos',
  });
  preencherSelect($('#f-situacao'), opcoes.situacoes, {
    valor: (s) => s,
    rotulo: (s) => s,
    vazio: 'Todas',
  });

  atualizarCargosEUfs();
}

/* --------------------------------------------------------------- consulta */

function parametros(extra = {}) {
  const p = new URLSearchParams();
  Object.entries({ ...estado.filtros, ...extra }).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) p.set(k, v);
  });
  return p;
}

async function consultar() {
  const corpo = $('#corpo');
  corpo.textContent = '';
  corpo.append(criar('tr', {}, criar('td', {
    colspan: String(Math.max(1, colunasVisiveis().length)),
    classe: 'carregando',
    texto: 'Carregando…',
  })));

  try {
    let dados;
    if (fonte.modo === 'api') {
      const p = parametros({
        pagina: estado.pagina,
        limite: estado.limite,
        ordem: estado.ordem,
        direcao: estado.direcao,
      });
      dados = await pegar(`api/candidatos?${p}`);
      $('#link-csv').href =
        `api/candidatos.csv?${parametros({ ordem: estado.ordem, direcao: estado.direcao })}`;
    } else {
      const recorte = await fonte.grade(estado.filtros);
      dados = fonte.filtrarLocalmente(recorte.candidatos, estado.filtros, {
        ordem: estado.ordem,
        direcao: estado.direcao,
        pagina: estado.pagina,
        limite: estado.limite,
      });
      // Sem servidor para montar o CSV, ele é gerado aqui mesmo.
      prepararCsvLocal(fonte.filtrarLocalmente(recorte.candidatos, estado.filtros, {
        ordem: estado.ordem, direcao: estado.direcao, pagina: 1, limite: 1e9,
      }).candidatos);
    }
    estado.ultimoResultado = dados;
    desenharTabela(dados);
  } catch (erro) {
    corpo.textContent = '';
    corpo.append(criar('tr', {}, criar('td', {
      colspan: String(Math.max(1, colunasVisiveis().length)),
      classe: 'erro',
      texto: `Não foi possível consultar: ${erro.message}`,
    })));
  }
}

/** Monta o CSV no navegador, já que não há servidor para gerá-lo. */
function prepararCsvLocal(candidatos) {
  const fixas = ['chave', 'ano_eleicao', 'nr_candidato', 'nm_candidato', 'nm_urna',
                 'ds_cargo', 'sg_uf', 'nm_ue', 'sg_partido', 'nm_partido', 'nm_coligacao',
                 'ds_situacao_candidatura', 'ds_genero', 'dt_nascimento', 'ds_cor_raca',
                 'ds_ocupacao', 'ds_grau_instrucao', 'qtd_bens', 'total_bens'];
  const externas = estado.colunas.filter((c) => c.tipo === 'externo').map((c) => c.id);

  const escapar = (v) => {
    const texto = v === null || v === undefined ? '' : String(v);
    return /[";\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
  };

  const linhas = [[...fixas, ...externas].join(';')];
  candidatos.forEach((c) => {
    const celulas = fixas.map((campo) => escapar(c[campo]));
    externas.forEach((id) => celulas.push(escapar((c.externos[id] || {}).valor)));
    linhas.push(celulas.join(';'));
  });

  // BOM para o Excel abrir acentuação corretamente.
  const blob = new Blob(['\ufeff' + linhas.join('\r\n')],
                        { type: 'text/csv;charset=utf-8' });
  const link = $('#link-csv');
  if (link.dataset.url) URL.revokeObjectURL(link.dataset.url);
  link.dataset.url = URL.createObjectURL(blob);
  link.href = link.dataset.url;
  link.download = `meucandidato-${fonte.arquivoDoRecorte(estado.filtros)}.csv`;
}

function colunasVisiveis() {
  return estado.colunas.filter((c) => estado.mostrarPesadas || c.peso !== 'pesada');
}

/* ---------------------------------------------------------------- tabela */

function desenharCabecalho() {
  const linha = $('#cabecalho');
  linha.textContent = '';
  linha.append(criar('th', { texto: '', style: 'width:34px' }));

  let grupoAnterior = null;
  colunasVisiveis().forEach((coluna) => {
    const ordenavel = coluna.tipo !== 'externo';
    // O nome do grupo aparece uma vez, na primeira coluna dele.
    const rotuloGrupo = coluna.grupo === grupoAnterior ? '' : (coluna.grupo || '');
    grupoAnterior = coluna.grupo;
    const seta = estado.ordem === coluna.id ? (estado.direcao === 'asc' ? ' ▲' : ' ▼') : '';
    const th = criar('th', {
      classe: [coluna.fixa ? 'coluna-fixa' : '', estado.ordem === coluna.id ? 'ordenada' : '']
        .filter(Boolean).join(' '),
      style: coluna.largura ? `min-width:${coluna.largura}px` : null,
      title: ordenavel ? 'Clique para ordenar' : 'Coluna preenchida por importação externa',
    }, [
      criar('span', { classe: 'grupo', texto: rotuloGrupo }),
      document.createTextNode(coluna.titulo + seta),
    ]);

    if (ordenavel) {
      th.addEventListener('click', () => {
        if (estado.ordem === coluna.id) {
          estado.direcao = estado.direcao === 'asc' ? 'desc' : 'asc';
        } else {
          estado.ordem = coluna.id;
          estado.direcao = 'asc';
        }
        estado.pagina = 1;
        consultar();
      });
    } else {
      th.style.cursor = 'default';
    }
    linha.append(th);
  });
}

function celulaExterna(coluna, candidato) {
  const item = candidato.externos[coluna.id];
  if (item && item.valor) {
    const conteudo = item.url
      ? criar('a', { href: item.url, target: '_blank', rel: 'noreferrer', texto: item.valor })
      : criar('span', { texto: item.valor });
    const td = criar('td', { title: item.observacao || '' }, conteudo);
    // O destaque marca fato conclusivo, nao qualquer mencao. Processo em
    // andamento nao e condenacao, e a planilha nao deve sugerir que seja.
    const conclusivo = /conden|ineleg|rejeitad|mandado de pris|implicaç[ãa]o eleitoral|^consta\b|sanç(ão|ões)/i;
    const negativo = /^0\b|nada consta|nada encontrado|nenhum(a)? /i;
    if (conclusivo.test(item.valor) && !negativo.test(item.valor)) {
      conteudo.className = 'marca atencao';
    }
    return td;
  }

  // Sem dado coletado: oferece a consulta manual na fonte.
  const url = linkManual(coluna.fonte, candidato);
  const fonte = estado.fontes[coluna.fonte];
  const td = criar('td', { classe: 'sem-dado' });
  td.append(document.createTextNode('sem dado '));
  if (url) {
    td.append(criar('a', {
      href: url,
      target: '_blank',
      rel: 'noreferrer',
      texto: '· consultar',
      title: `Abrir ${fonte ? fonte.nome : coluna.fonte} para conferência manual`,
    }));
  }
  return td;
}

function celula(coluna, candidato) {
  if (coluna.tipo === 'externo') return celulaExterna(coluna, candidato);

  const valor = candidato[coluna.id];

  if (coluna.id === 'nm_urna') {
    const conteudo = criar('div', { classe: 'celula-nome' }, [
      criar('strong', { texto: valor || candidato.nm_candidato || '—' }),
    ]);
    if (candidato.url_divulgacand) {
      // Enquanto o modelo de link direto não for conferido contra o site do
      // TSE, o link abre a busca do portal — e o texto diz isso, para não
      // prometer uma página de candidato que não vai aparecer.
      const conferido = (estado.links.perfil_candidato || {}).verificado;
      conteudo.append(criar('a', {
        href: candidato.url_divulgacand,
        target: '_blank',
        rel: 'noreferrer',
        title: conferido
          ? 'Abrir o registro no DivulgaCandContas do TSE'
          : `Abrir a busca do DivulgaCandContas — procure por "${candidato.nm_candidato || candidato.nm_urna}". `
            + 'O link direto para a página do candidato ainda não foi mapeado.',
        texto: conferido ? '↗' : '⌕',
      }));
    }
    return criar('td', { classe: 'coluna-fixa' }, conteudo);
  }

  if (coluna.tipo === 'moeda') {
    return criar('td', { classe: 'numero', texto: formatarMoeda(valor) });
  }
  if (coluna.tipo === 'numero') {
    return criar('td', { classe: 'numero', texto: formatarNumero(valor) });
  }
  if (coluna.tipo === 'data') {
    return criar('td', { texto: formatarData(valor) });
  }

  if (coluna.id === 'ds_situacao_candidatura' && valor) {
    const atencao = /indeferid|cassad|renunc|falecid|impugnad/i.test(valor);
    return criar('td', {}, criar('span', {
      classe: `marca${atencao ? ' atencao' : ''}`,
      texto: valor,
    }));
  }

  return criar('td', { texto: valor === null || valor === undefined ? '' : String(valor) });
}

function desenharTabela(dados) {
  desenharCabecalho();

  const corpo = $('#corpo');
  corpo.textContent = '';

  $('#vazio').hidden = dados.total > 0;
  $('#resumo-consulta').textContent = dados.total
    ? `${formatarNumero(dados.total)} candidato(s) — página ${dados.pagina} de ${dados.paginas}`
    : '';

  dados.candidatos.forEach((candidato) => {
    const linha = criar('tr');
    const botao = criar('button', {
      classe: 'botao-expandir',
      type: 'button',
      title: 'Ver bens declarados e demais fontes',
      texto: '+',
    });
    linha.append(criar('td', {}, botao));
    colunasVisiveis().forEach((coluna) => linha.append(celula(coluna, candidato)));
    corpo.append(linha);

    let expandida = null;
    botao.addEventListener('click', async () => {
      if (expandida) {
        expandida.remove();
        expandida = null;
        botao.textContent = '+';
        return;
      }
      botao.textContent = '−';
      expandida = criar('tr', { classe: 'detalhe' });
      const td = criar('td', {
        colspan: String(colunasVisiveis().length + 1),
        classe: 'carregando',
        texto: 'Carregando detalhes…',
      });
      expandida.append(td);
      linha.after(expandida);
      try {
        let detalhe;
        if (fonte.modo === 'api') {
          detalhe = await pegar(`api/candidato/${encodeURIComponent(candidato.chave)}`);
        } else {
          // No modo estático a linha já traz tudo menos os bens, que vêm
          // num arquivo por recorte, buscado na primeira expansão.
          const bens = await fonte.bens(estado.filtros);
          detalhe = { ...candidato, bens: bens[candidato.chave] || [] };
        }
        td.className = '';
        td.textContent = '';
        td.append(painelDetalhe(detalhe));
      } catch (erro) {
        td.className = 'erro';
        td.textContent = `Não foi possível carregar: ${erro.message}`;
      }
    });
  });

  $('#paginacao').hidden = dados.paginas <= 1;
  $('#info-pagina').textContent = `Página ${dados.pagina} de ${dados.paginas}`;
  $('#btn-anterior').disabled = dados.pagina <= 1;
  $('#btn-proxima').disabled = dados.pagina >= dados.paginas;
}

/* ------------------------------------------------------------- expansao */

function par(rotulo, valor) {
  return criar('div', { classe: 'par' }, [
    criar('dt', { texto: rotulo }),
    criar('dd', { texto: valor === null || valor === undefined || valor === '' ? '—' : String(valor) }),
  ]);
}

function painelDetalhe(c) {
  const painel = criar('div', { classe: 'painel' });

  painel.append(criar('h4', { texto: 'Cadastro no TSE' }));
  painel.append(criar('dl', { classe: 'painel-grade' }, [
    par('Nome completo', c.nm_candidato),
    par('Nome social', c.nm_social),
    par('Número', c.nr_candidato),
    par('Partido', [c.sg_partido, c.nm_partido].filter(Boolean).join(' — ')),
    par('Federação', [c.sg_federacao, c.nm_federacao].filter(Boolean).join(' — ')),
    par('Coligação', c.nm_coligacao),
    par('Composição', c.ds_composicao_coligacao),
    par('Cargo', c.ds_cargo),
    par('Unidade eleitoral', [c.nm_ue, c.sg_uf].filter(Boolean).join(' / ')),
    par('Situação do registro', c.ds_situacao_candidatura),
    par('Detalhe', c.ds_detalhe_situacao_cand),
    par('Situação final', c.ds_situacao_candidato_tot),
    par('Nascimento', c.dt_nascimento),
    par('Idade na posse', c.nr_idade_data_posse),
    par('Município natal', [c.nm_municipio_nascimento, c.sg_uf_nascimento].filter(Boolean).join(' / ')),
    par('Gênero', c.ds_genero),
    par('Cor/raça', c.ds_cor_raca),
    par('Estado civil', c.ds_estado_civil),
    par('Escolaridade', c.ds_grau_instrucao),
    par('Ocupação declarada', c.ds_ocupacao),
    par('Reeleição', c.st_reeleicao),
    par('Limite de gasto declarado', formatarMoeda(c.vr_despesa_max_campanha)),
    par('Identificador', c.chave),
  ]));

  painel.append(criar('h4', {
    texto: `Bens declarados — ${formatarNumero(c.qtd_bens)} item(ns), total ${formatarMoeda(c.total_bens)}`,
  }));
  if (c.bens.length) {
    const tabela = criar('table');
    tabela.append(criar('thead', {}, criar('tr', {}, [
      criar('th', { texto: '#' }),
      criar('th', { texto: 'Tipo' }),
      criar('th', { texto: 'Descrição' }),
      criar('th', { texto: 'Valor' }),
    ])));
    const corpo = criar('tbody');
    c.bens.forEach((bem) => {
      corpo.append(criar('tr', {}, [
        criar('td', { texto: String(bem.nr_ordem ?? '') }),
        criar('td', { texto: bem.ds_tipo || '' }),
        criar('td', { texto: bem.ds_bem || '' }),
        criar('td', { classe: 'numero', texto: formatarMoeda(bem.vr_bem) }),
      ]));
    });
    tabela.append(corpo);
    painel.append(tabela);
  } else {
    painel.append(criar('p', { classe: 'sem-dado', texto: 'Nenhum bem declarado no registro.' }));
  }

  painel.append(criar('h4', { texto: 'Outras fontes' }));
  const grade = criar('div', { classe: 'painel-grade' });
  estado.colunas.filter((col) => col.tipo === 'externo').forEach((coluna) => {
    const item = c.externos[coluna.id];
    const bloco = criar('div', { classe: 'par' });
    bloco.append(criar('dt', { texto: coluna.titulo }));
    const dd = criar('dd');
    if (item && item.valor) {
      dd.append(item.url
        ? criar('a', { href: item.url, target: '_blank', rel: 'noreferrer', texto: item.valor })
        : document.createTextNode(item.valor));
      if (item.observacao) dd.append(criar('div', { classe: 'sem-dado', texto: item.observacao }));
      if (item.coletado_em) {
        dd.append(criar('div', {
          classe: 'sem-dado',
          texto: `coletado em ${formatarDataHora(item.coletado_em)}`,
        }));
      }
    } else {
      dd.append(criar('span', { classe: 'sem-dado', texto: 'sem dado importado ' }));
      const url = linkManual(coluna.fonte, c);
      if (url) {
        dd.append(criar('a', { href: url, target: '_blank', rel: 'noreferrer', texto: '· consultar na fonte' }));
      }
    }
    bloco.append(dd);
    grade.append(bloco);
  });
  painel.append(grade);

  return painel;
}

/* ----------------------------------------------------------------- paineis */

function abrirModal(titulo, conteudo) {
  $('#modal-titulo').textContent = titulo;
  const corpo = $('#modal-corpo');
  corpo.textContent = '';
  corpo.append(conteudo);
  $('#modal').hidden = false;
}

function painelFontes() {
  const raiz = criar('div');
  raiz.append(criar('p', {
    classe: 'ajuda',
    texto: 'De onde vem cada coluna da planilha. Fontes sem interface programática oficial '
         + 'são preenchidas por importação externa; enquanto não houver dado importado, a '
         + 'planilha mostra o link para conferência manual.',
  }));

  const tabela = criar('table');
  tabela.append(criar('thead', {}, criar('tr', {}, [
    criar('th', { texto: 'Fonte' }),
    criar('th', { texto: 'Categoria' }),
    criar('th', { texto: 'API oficial' }),
    criar('th', { texto: 'O que traz' }),
  ])));
  const corpo = criar('tbody');
  Object.values(estado.fontes).forEach((f) => {
    corpo.append(criar('tr', {}, [
      criar('td', {}, criar('a', { href: f.url, target: '_blank', rel: 'noreferrer', texto: f.nome })),
      criar('td', { texto: f.categoria || '' }),
      criar('td', {}, criar('span', {
        classe: f.tem_api ? 'marca' : 'marca atencao',
        texto: f.tem_api ? 'sim' : 'não',
      })),
      criar('td', { texto: f.descricao || '' }),
    ]));
  });
  tabela.append(corpo);
  raiz.append(tabela);
  return raiz;
}

function painelProcedencia() {
  const p = estado.procedencia;
  const raiz = criar('div');

  raiz.append(criar('p', {
    classe: 'ajuda',
    texto: 'Cada arquivo importado fica registrado com data, tamanho e SHA-256 do conteúdo. '
         + 'Baixando o mesmo arquivo na fonte original e recalculando o hash, dá para conferir '
         + 'que a base carregada aqui é idêntica ao que a fonte publicou.',
  }));

  raiz.append(criar('dl', { classe: 'painel-grade' }, [
    par('Origem da base', p.origem_base),
    par('Base atualizada em', formatarDataHora(p.atualizado_em)),
    par('Dados externos em', formatarDataHora(p.externos_atualizados_em)),
    par('Candidatos', formatarNumero(p.totais.candidatos)),
    par('Bens declarados', formatarNumero(p.totais.bens)),
    par('Registros externos', formatarNumero(p.totais.dados_externos)),
  ]));

  if (p.cobertura_externa.length) {
    raiz.append(criar('h4', { texto: 'Cobertura das colunas externas' }));
    const tab = criar('table');
    tab.append(criar('thead', {}, criar('tr', {}, [
      criar('th', { texto: 'Fonte' }),
      criar('th', { texto: 'Campo' }),
      criar('th', { texto: 'Registros' }),
      criar('th', { texto: 'Coleta mais recente' }),
    ])));
    const corpo = criar('tbody');
    p.cobertura_externa.forEach((c) => {
      corpo.append(criar('tr', {}, [
        criar('td', { texto: c.fonte }),
        criar('td', { texto: c.campo }),
        criar('td', { classe: 'numero', texto: formatarNumero(c.registros) }),
        criar('td', { texto: formatarDataHora(c.ultimo) }),
      ]));
    });
    tab.append(corpo);
    raiz.append(tab);
  }

  raiz.append(criar('h4', { texto: 'Importações' }));
  const tabela = criar('table');
  tabela.append(criar('thead', {}, criar('tr', {}, [
    criar('th', { texto: 'Quando' }),
    criar('th', { texto: 'Tipo' }),
    criar('th', { texto: 'Arquivo' }),
    criar('th', { texto: 'Linhas' }),
    criar('th', { texto: 'SHA-256' }),
  ])));
  const corpo = criar('tbody');
  p.importacoes.forEach((imp) => {
    corpo.append(criar('tr', {}, [
      criar('td', { texto: formatarDataHora(imp.concluido_em || imp.iniciado_em) }),
      criar('td', { texto: imp.tipo }),
      criar('td', { texto: imp.arquivo || '' }),
      criar('td', { classe: 'numero', texto: formatarNumero(imp.linhas_gravadas) }),
      criar('td', {}, criar('code', { texto: imp.sha256 || '' })),
    ]));
  });
  tabela.append(corpo);
  raiz.append(tabela);
  return raiz;
}

/* ------------------------------------------------------------------ eventos */

function ligarEventos() {
  $('#f-ano').addEventListener('change', atualizarCargosEUfs);
  $('#f-cargo').addEventListener('change', atualizarUfs);
  $('#f-uf').addEventListener('change', atualizarUnidades);

  $('#form-filtros').addEventListener('submit', (evento) => {
    evento.preventDefault();
    const erro = $('#erro-filtros');
    const cargo = $('#f-cargo').value;
    const uf = $('#f-uf').value;

    if (!cargo || !uf) {
      erro.hidden = false;
      erro.textContent = 'Cargo e UF são obrigatórios para montar a planilha.';
      return;
    }
    if (CARGOS_MUNICIPAIS.includes(Number(cargo)) && !$('#f-ue').value) {
      erro.hidden = false;
      erro.textContent = 'Para cargos municipais, escolha também o município.';
      return;
    }
    erro.hidden = true;

    estado.filtros = {
      ano: $('#f-ano').value,
      cargo,
      uf,
      ue: $('#f-ue').value,
      nome: $('#f-nome').value.trim(),
      partido: $('#f-partido').value,
      situacao: $('#f-situacao').value,
    };
    estado.pagina = 1;
    $('#tela-filtros').hidden = true;
    $('#tela-resultado').hidden = false;
    consultar();
  });

  $('#btn-voltar').addEventListener('click', () => {
    $('#tela-resultado').hidden = true;
    $('#tela-filtros').hidden = false;
  });

  $('#chk-pesadas').addEventListener('change', (e) => {
    estado.mostrarPesadas = e.target.checked;
    if (estado.ultimoResultado) desenharTabela(estado.ultimoResultado);
  });

  $('#btn-anterior').addEventListener('click', () => {
    if (estado.pagina > 1) { estado.pagina -= 1; consultar(); }
  });
  $('#btn-proxima').addEventListener('click', () => {
    estado.pagina += 1;
    consultar();
  });

  document.querySelectorAll('[data-painel]').forEach((link) => {
    link.addEventListener('click', (evento) => {
      evento.preventDefault();
      const qual = link.dataset.painel;
      if (qual === 'fontes') abrirModal('Fontes de dados', painelFontes());
      if (qual === 'procedencia') abrirModal('Procedência dos dados', painelProcedencia());
    });
  });

  const fechar = () => { $('#modal').hidden = true; };
  $('#modal-fechar').addEventListener('click', fechar);
  $('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) fechar(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
}

/* --------------------------------------------------------------- inicio */

(async function iniciar() {
  ligarEventos();
  try {
    await carregarBase();
  } catch (erro) {
    const alvo = $('#erro-filtros');
    alvo.hidden = false;
    alvo.textContent = `Não foi possível carregar a base: ${erro.message}. `
      + 'Gere os dados com scripts/gerar_exemplo.py ou scripts/importar_tse.py.';
  }
})();
