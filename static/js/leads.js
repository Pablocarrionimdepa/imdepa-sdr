/**
 * Imdepa SDR Agent - Leads Admin Panel JavaScript
 */

(function () {
    'use strict';

    const leadsBody = document.getElementById('leadsBody');
    const leadsTable = document.getElementById('leadsTable');
    const emptyState = document.getElementById('emptyState');
    const searchInput = document.getElementById('searchInput');
    const statusFilter = document.getElementById('statusFilter');
    const segmentFilter = document.getElementById('segmentFilter');
    const refreshBtn = document.getElementById('refreshBtn');
    const exportBtn = document.getElementById('exportBtn');
    const modalOverlay = document.getElementById('modalOverlay');
    const modalBody = document.getElementById('modalBody');
    const modalClose = document.getElementById('modalClose');
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');

    const totalLeadsEl = document.getElementById('totalLeads');
    const newLeadsEl = document.getElementById('newLeads');
    const qualifiedLeadsEl = document.getElementById('qualifiedLeads');

    let allLeads = [];

    async function fetchLeads() {
        try {
            const res = await fetch('/api/leads');
            const data = await res.json();
            allLeads = data.leads || [];
            updateStats();
            renderLeads();
        } catch (err) {
            console.error('Erro ao buscar leads:', err);
        }
    }

    function updateStats() {
        totalLeadsEl.textContent = allLeads.length;
        newLeadsEl.textContent = allLeads.filter((l) => l.status === 'novo').length;
        qualifiedLeadsEl.textContent = allLeads.filter((l) => l.status === 'qualificado').length;
    }

    function getStatusLabel(status) {
        const labels = {
            novo: 'Novo',
            qualificado: 'Qualificado',
            ACTIVE: 'Active',
            INACTIVE: 'Inactive',
        };
        return labels[status] || status || '-';
    }

    function renderLeads() {
        const search = searchInput.value.toLowerCase().trim();
        const statusVal = statusFilter.value;
        const segmentVal = segmentFilter.value;

        const filtered = allLeads.filter((lead) => {
            if (search) {
                const haystack = [
                    lead.empresa,
                    lead.contato,
                    lead.email,
                    lead.telefone,
                    lead.segmento,
                    lead.produtos_interesse,
                    lead.cnpj,
                ].join(' ').toLowerCase();
                if (!haystack.includes(search)) return false;
            }

            if (statusVal && lead.status !== statusVal) return false;
            if (segmentVal && !lead.segmento.toLowerCase().includes(segmentVal.toLowerCase())) return false;
            return true;
        });

        if (filtered.length === 0) {
            leadsTable.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        leadsTable.style.display = 'table';
        emptyState.style.display = 'none';

        leadsBody.innerHTML = filtered.map((lead) => `
            <tr>
                <td class="td-empresa">${escapeHtml(lead.empresa || '-')}</td>
                <td class="td-contato">${escapeHtml(lead.contato || '-')}</td>
                <td class="td-segmento">${escapeHtml(lead.segmento || '-')}</td>
                <td class="td-produtos" title="${escapeHtml(lead.produtos_interesse || '')}">${escapeHtml(lead.produtos_interesse || '-')}</td>
                <td class="td-volume">${escapeHtml(lead.volume_compra || '-')}</td>
                <td><span class="status-badge ${lead.status}">${getStatusLabel(lead.status)}</span></td>
                <td>${formatDate(lead.updated_at)}</td>
                <td>
                    <div class="action-btns">
                        <button class="btn-view" title="Ver detalhes" onclick="viewLead('${lead.session_id}')">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                        </button>
                        <button class="btn-delete" title="Excluir" onclick="deleteLead(${lead.id})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    window.viewLead = async function (sessionId) {
        try {
            const res = await fetch(`/api/leads/${sessionId}/history`);
            const data = await res.json();
            const lead = data.lead;
            const messages = data.messages || [];
            const historyHtml = messages.length
                ? messages.map((message) => `
                    <div class="conversation-message ${message.role}">
                        <div class="conversation-role">${message.role === 'assistant' ? 'Fernanda' : 'Cliente'}</div>
                        <div class="conversation-content">${escapeHtml(message.content || '')}</div>
                        <div class="conversation-date">${formatDate(message.created_at)}</div>
                    </div>
                `).join('')
                : '<div class="detail-value">Nenhuma mensagem registrada.</div>';

            modalBody.innerHTML = `
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Empresa</span>
                        <div class="detail-value">${escapeHtml(lead.empresa || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Contato</span>
                        <div class="detail-value">${escapeHtml(lead.contato || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">E-mail</span>
                        <div class="detail-value">${escapeHtml(lead.email || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Telefone</span>
                        <div class="detail-value">${escapeHtml(lead.telefone || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">CNPJ</span>
                        <div class="detail-value">${escapeHtml(lead.cnpj || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Segmento</span>
                        <div class="detail-value">${escapeHtml(lead.segmento || '')}</div>
                    </div>
                    <div class="detail-item full">
                        <span class="detail-label">Produtos de Interesse</span>
                        <div class="detail-value">${escapeHtml(lead.produtos_interesse || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Volume de Compra</span>
                        <div class="detail-value">${escapeHtml(lead.volume_compra || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Fornecedor Atual</span>
                        <div class="detail-value">${escapeHtml(lead.fornecedor_atual || '')}</div>
                    </div>
                    <div class="detail-item full">
                        <span class="detail-label">Dores e Necessidades</span>
                        <div class="detail-value">${escapeHtml(lead.dores_necessidades || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Decisor(es)</span>
                        <div class="detail-value">${escapeHtml(lead.decisores || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Proximo Passo</span>
                        <div class="detail-value">${escapeHtml(lead.proximo_passo || '')}</div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Status</span>
                        <div class="detail-value"><span class="status-badge ${lead.status}">${getStatusLabel(lead.status)}</span></div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Ultima Atualizacao</span>
                        <div class="detail-value">${formatDate(lead.updated_at)}</div>
                    </div>
                    <div class="detail-item full">
                        <span class="detail-label">Resumo Final da Qualificacao</span>
                        <div class="detail-value pre-line">${escapeHtml(lead.qualification_summary || '')}</div>
                    </div>
                    <div class="detail-item full">
                        <span class="detail-label">Historico Completo da Conversa</span>
                        <div class="conversation-history">${historyHtml}</div>
                    </div>
                </div>
            `;

            modalOverlay.classList.add('active');
        } catch (err) {
            console.error('Erro ao buscar lead:', err);
        }
    };

    window.deleteLead = async function (leadId) {
        if (!confirm('Tem certeza que deseja excluir este lead?')) return;

        try {
            const res = await fetch(`/api/leads/${leadId}`, { method: 'DELETE' });
            if (res.ok) {
                await fetchLeads();
            }
        } catch (err) {
            console.error('Erro ao excluir lead:', err);
        }
    };

    function exportCSV() {
        if (allLeads.length === 0) {
            alert('Nenhum lead para exportar.');
            return;
        }

        const headers = [
            'Empresa', 'Contato', 'E-mail', 'Telefone', 'CNPJ', 'Segmento', 'Produtos de Interesse',
            'Volume de Compra', 'Fornecedor Atual', 'Dores e Necessidades',
            'Decisores', 'Proximo Passo', 'Status', 'Data Criacao', 'Ultima Atualizacao',
        ];

        const rows = allLeads.map((l) => [
            l.empresa,
            l.contato,
            l.email,
            l.telefone,
            l.cnpj,
            l.segmento,
            l.produtos_interesse,
            l.volume_compra,
            l.fornecedor_atual,
            l.dores_necessidades,
            l.decisores,
            l.proximo_passo,
            l.status,
            l.created_at,
            l.updated_at,
        ]);

        let csv = '\uFEFF';
        csv += headers.map((h) => `"${h}"`).join(';') + '\n';
        rows.forEach((row) => {
            csv += row.map((cell) => `"${(cell || '').replace(/"/g, '""')}"`).join(';') + '\n';
        });

        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leads_imdepa_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch {
            return dateStr;
        }
    }

    searchInput.addEventListener('input', renderLeads);
    statusFilter.addEventListener('change', renderLeads);
    segmentFilter.addEventListener('change', renderLeads);
    refreshBtn.addEventListener('click', fetchLeads);
    exportBtn.addEventListener('click', exportCSV);

    modalClose.addEventListener('click', () => {
        modalOverlay.classList.remove('active');
    });

    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) {
            modalOverlay.classList.remove('active');
        }
    });

    menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 && sidebar.classList.contains('open')) {
            if (!sidebar.contains(e.target) && e.target !== menuToggle) {
                sidebar.classList.remove('open');
            }
        }
    });

    fetchLeads();
    setInterval(fetchLeads, 30000);
})();
