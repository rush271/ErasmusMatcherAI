let currentContext = {};
let currentTableResults = [];
let chatHistory = [];
let lastQuestion = '';
let lastAnswer   = '';
let sessionFacts = [];

function goHome() {
    document.body.classList.remove('searched');
    hide('results-section');
    hide('loading');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Setup hero chat input on page load
document.addEventListener('DOMContentLoaded', () => {
    const heroInput = document.getElementById('hero-input');
    const heroBtn   = document.getElementById('hero-send-btn');

    heroInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 100) + 'px';
    });
    heroInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); heroBtn.click(); }
    });
    heroBtn.addEventListener('click', submitHeroChat);
});

function submitHeroChat() {
    const input    = document.getElementById('hero-input');
    const errorDiv = document.getElementById('hero-error');
    const userText = input.value.trim();
    if (!userText) return;

    errorDiv.classList.add('hidden');
    document.body.classList.add('searched');
    show('loading');
    hide('results-section');
    document.getElementById('results-list').innerHTML = '';

    fetch('/api/parse_query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: userText })
    })
    .then(r => r.json().then(d => ({ ok: r.ok, d })))
    .then(({ ok, d }) => {
        if (!ok) {
            document.body.classList.remove('searched');
            hide('loading');
            const missing = d.missing || [];
            if (d.error && d.error !== 'parse_failed') {
                errorDiv.textContent = 'Σφάλμα: ' + d.error;
            } else if (missing.includes('πανεπιστήμιο') && missing.includes('εξάμηνο')) {
                errorDiv.textContent = 'Παρακαλώ ανέφερε πανεπιστήμιο και εξάμηνο που θες να πας, π.χ. "Aalto, 6ο εξάμηνο".';
            } else if (missing.includes('πανεπιστήμιο')) {
                errorDiv.textContent = 'Δεν κατάλαβα ποιο πανεπιστήμιο. Δοκίμασε "Aalto", "UPM" ή "TU Delft".';
            } else {
                errorDiv.textContent = 'Δεν κατάλαβα το εξάμηνο. Ανέφερε π.χ. "6ο εξάμηνο".';
            }
            errorDiv.classList.remove('hidden');
            return;
        }

        return fetch('/api/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_university: 'AUTH', semester: d.semester, target_university: d.university })
        })
        .then(r => r.json())
        .then(data => {
            hide('loading');
            if (data.error) {
                document.body.classList.remove('searched');
                errorDiv.textContent = data.error;
                errorDiv.classList.remove('hidden');
                return;
            }
            currentContext = {
                source_university: data.source_university,
                target_university: data.target_university,
                semester: data.semester
            };
            currentTableResults = data.results.map((r, i) => ({
                index: i + 1,
                source: r.source.title,
                source_ects: r.source.ects,
                match: r.matches[0]?.title || null,
                match_ects: r.matches[0]?.ects || null,
                score: r.matches[0]?.score || null
            }));
            chatHistory = [];
            renderResults(data, userText);
        });
    })
    .catch(() => {
        document.body.classList.remove('searched');
        hide('loading');
        errorDiv.textContent = 'Σφάλμα σύνδεσης. Δοκίμασε ξανά.';
        errorDiv.classList.remove('hidden');
    });
}


function renderResults(data, initialUserMessage = null) {
    const list = document.getElementById('results-list');
    list.innerHTML = '';

    const total   = data.total_courses;
    const MATCH_THRESHOLD = 55;
    const matched = data.results.filter(r => r.matches[0]?.score >= MATCH_THRESHOLD).length;
    let tier = matched >= 4 ? 'green' : matched >= 2 ? 'yellow' : 'red';

    const resultRow = document.createElement('div');
    resultRow.className = 'result-row';
    resultRow.style.animationDelay = '0.05s';

    const number = document.createElement('div');
    number.className = 'result-number';
    number.textContent = '1.';

    const box = document.createElement('div');
    box.className = `uni-box ${tier}`;

    const coursesCol = document.createElement('div');
    coursesCol.className = 'courses-col';

    const header = document.createElement('div');
    header.className = 'uni-header';
    header.innerHTML = `<span class="uni-name">${data.target_university}</span>`;
    coursesCol.appendChild(header);

    const coursesList = document.createElement('div');
    coursesList.className = 'courses-list';

    data.results.forEach((result, idx) => {
        coursesList.appendChild(buildCourseRow(result, idx + 1));
    });
    coursesCol.appendChild(coursesList);

    // Score column (top section only, alongside courses)
    const scoreCol = document.createElement('div');
    scoreCol.className = `score-col ${tier}`;
    const scoreNum = document.createElement('span');
    scoreNum.className = 'score-num';
    scoreNum.textContent = `${matched}/${total}`;
    const scoreLabel = document.createElement('span');
    scoreLabel.className = 'score-label';
    scoreLabel.textContent = 'match';
    scoreCol.appendChild(scoreNum);
    scoreCol.appendChild(scoreLabel);

    const topSection = document.createElement('div');
    topSection.className = 'uni-box-top';
    topSection.dataset.role = 'top-section';
    topSection.appendChild(coursesCol);
    topSection.appendChild(scoreCol);

    // Chat area — full width, below courses+score
    const chatArea = document.createElement('div');
    chatArea.className = 'chat-area';

    // Chat messages area — εμφανίζεται αμέσως με greeting
    const chatMessages = document.createElement('div');
    chatMessages.className = 'chat-messages';
    chatArea.appendChild(chatMessages);

    // Αυτόματο greeting + conversation flow
    const heroGreeting = `Γεια σου! Πες μου σε ποιό πανεπιστήμιο και σε ποιο εξάμηνο θέλεις να πας Erasmus.`;
    addChatMsg(chatMessages, 'ai', heroGreeting);

    if (initialUserMessage) {
        addChatMsg(chatMessages, 'user', initialUserMessage);
        const summary = `Βρήκα ${matched} από ${total} αντιστοιχίσεις για το ${data.semester}ο εξάμηνο στο ${data.target_university}! Δες την πλήρη λίστα παραπάνω. Θέλεις να μάθεις περισσότερα για κάποιο μάθημα;`;
        addChatMsg(chatMessages, 'ai', summary);
    }

    // Prompt input
    const promptWrap = document.createElement('div');
    promptWrap.className = 'prompt-input-wrap';
    const MAX_CHARS = 180;
    promptWrap.innerHTML = `
        <textarea class="prompt-textarea" rows="1" placeholder="Ask me anything…" aria-label="Ερώτηση στο AI" maxlength="${MAX_CHARS}"></textarea>
        <button class="prompt-send-btn" aria-label="Αποστολή">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
            </svg>
        </button>
        <span class="char-counter">0/${MAX_CHARS}</span>
    `;

    const textarea    = promptWrap.querySelector('textarea');
    const sendBtn     = promptWrap.querySelector('.prompt-send-btn');
    const charCounter = promptWrap.querySelector('.char-counter');

    textarea.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        const len = this.value.length;
        charCounter.textContent = `${len}/${MAX_CHARS}`;
        charCounter.style.color = len >= MAX_CHARS ? 'var(--red)' : '';
    });
    textarea.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendBtn.click();
        }
    });

    sendBtn.addEventListener('click', () => {
        const question = textarea.value.trim();
        if (!question) return;
        chatMessages.classList.remove('hidden');
        addChatMsg(chatMessages, 'user', question);
        textarea.value = '';
        textarea.style.height = 'auto';

        // Προσωρινό "typing..." μήνυμα
        const typingMsg = addChatMsg(chatMessages, 'ai', '');
        typingMsg.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';

        chatHistory.push({ role: 'user', content: question });
        lastQuestion = question;

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, history: chatHistory, context: currentContext, facts: sessionFacts, table_results: currentTableResults })
        })
        .then(r => r.json().then(data => ({ ok: r.ok, data })))
        .then(({ data }) => {
            if (data.redirect) {
                typingMsg.textContent = `Ψάχνω για ${data.redirect.university}, εξάμηνο ${data.redirect.semester}…`;
                fetch('/api/match', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_university: 'AUTH', semester: data.redirect.semester, target_university: data.redirect.university })
                })
                .then(r => r.json())
                .then(matchData => {
                    if (matchData.error) { typingMsg.textContent = matchData.error; return; }
                    currentContext = { source_university: matchData.source_university, target_university: matchData.target_university, semester: matchData.semester };
                    currentTableResults = matchData.results.map((r, i) => ({
                        index: i + 1,
                        source: r.source.title,
                        source_ects: r.source.ects,
                        match: r.matches[0]?.title || null,
                        match_ects: r.matches[0]?.ects || null,
                        score: r.matches[0]?.score || null
                    }));
                    refreshTable(matchData);
                    typingMsg.textContent = `Ενημέρωσα τον πίνακα για ${matchData.target_university}, εξάμηνο ${matchData.semester}ο. Βρήκα ${matchData.results.filter(r => r.matches[0]?.score >= 55).length}/${matchData.total_courses} αντιστοιχίσεις.`;
                    chatHistory.push({ role: 'assistant', content: typingMsg.textContent });
                });
                return;
            }
            typingMsg.textContent = data.answer || data.error || 'Κάτι πήγε στραβά.';
            if (data.answer) {
                chatHistory.push({ role: 'assistant', content: data.answer });
                lastAnswer = data.answer;
                if (data.new_fact && !sessionFacts.includes(data.new_fact)) sessionFacts.push(data.new_fact);
                addFeedbackButtons(typingMsg, lastQuestion, lastAnswer);
            }
        })
        .catch(err => { typingMsg.textContent = `Error: ${err.message}`; });
    });

    chatArea.appendChild(promptWrap);

    box.appendChild(topSection);
    box.appendChild(chatArea);

    resultRow.appendChild(number);
    resultRow.appendChild(box);
    list.appendChild(resultRow);

    show('results-section');
}

function addChatMsg(container, role, text) {
    const msg = document.createElement('div');
    msg.className = `chat-msg chat-msg-${role}`;
    msg.textContent = text;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    return msg;
}

function addFeedbackButtons(msgEl, question, answer) {
    const wrapper = document.createElement('div');
    wrapper.className = 'feedback-wrapper';
    wrapper.innerHTML = `
        <div class="feedback-row">
            <button class="feedback-btn feedback-icon" data-label="positive" title="Χρήσιμο">👍</button>
            <button class="feedback-btn feedback-icon" data-label="negative" title="Όχι χρήσιμο">👎</button>
        </div>
        <div class="feedback-correction hidden">
            <input class="correction-input" type="text" placeholder="Τι πήγε στραβά;" maxlength="120" />
            <button class="correction-send">↵</button>
        </div>
    `;
    msgEl.parentElement.insertBefore(wrapper, msgEl.nextSibling);

    const row            = wrapper.querySelector('.feedback-row');
    const correctionBox  = wrapper.querySelector('.feedback-correction');
    const correctionInput= wrapper.querySelector('.correction-input');
    const correctionSend = wrapper.querySelector('.correction-send');

    let activeLabel = null;

    const sendFeedback = (label, correction = '') => {
        fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, answer, label, correction })
        });
    };

    const clearActive = () => {
        row.querySelectorAll('.feedback-btn').forEach(b => {
            b.classList.remove('active-pos', 'active-neg');
        });
        correctionBox.classList.add('hidden');
        correctionInput.value = '';
        activeLabel = null;
    };

    row.querySelectorAll('.feedback-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const label = btn.dataset.label;
            if (activeLabel === label) { clearActive(); return; }
            clearActive();
            activeLabel = label;
            btn.classList.add(label === 'positive' ? 'active-pos' : 'active-neg');
            if (label === 'negative') {
                correctionBox.classList.remove('hidden');
                correctionInput.focus();
            }
            // 👍 είναι μόνο visual — δεν στέλνει τίποτα στο backend
        });
    });

    const submitCorrection = () => {
        sendFeedback('negative', correctionInput.value.trim());
        correctionBox.innerHTML = '<span style="color:var(--text-2);font-size:12px;">Ευχαριστούμε για το feedback!</span>';
    };
    correctionSend.addEventListener('click', submitCorrection);
    correctionInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitCorrection(); });
}

function refreshTable(data) {
    const topSection = document.querySelector('[data-role="top-section"]');
    if (!topSection) return;
    topSection.classList.add('refreshing');
    topSection.addEventListener('animationend', () => topSection.classList.remove('refreshing'), { once: true });

    const total   = data.total_courses;
    const MATCH_THRESHOLD = 55;
    const matched = data.results.filter(r => r.matches[0]?.score >= MATCH_THRESHOLD).length;
    const tier    = matched >= 4 ? 'green' : matched >= 2 ? 'yellow' : 'red';

    // Update box tier color
    const box = topSection.closest('.uni-box');
    box.className = `uni-box ${tier}`;

    // Rebuild courses-col
    const coursesCol = document.createElement('div');
    coursesCol.className = 'courses-col';
    const header = document.createElement('div');
    header.className = 'uni-header';
    header.innerHTML = `<span class="uni-name">${data.target_university}</span>`;
    coursesCol.appendChild(header);
    const coursesList = document.createElement('div');
    coursesList.className = 'courses-list';
    data.results.forEach((result, idx) => {
        coursesList.appendChild(buildCourseRow(result, idx + 1));
    });
    coursesCol.appendChild(coursesList);

    // Rebuild score-col
    const scoreCol = document.createElement('div');
    scoreCol.className = `score-col ${tier}`;
    scoreCol.innerHTML = `<span class="score-num">${matched}/${total}</span><span class="score-label">match</span>`;

    topSection.innerHTML = '';
    topSection.appendChild(coursesCol);
    topSection.appendChild(scoreCol);
}

// Χτίζει concept graph SVG μεταξύ δύο μαθημάτων
function buildConceptGraph(src, m) {
    const parseTerms = str => (str || '').split(',').map(t => t.trim()).filter(Boolean);
    const srcTerms = [...new Set([...parseTerms(src.topics), ...parseTerms(src.keywords)])].slice(0, 10);
    const tgtTerms = [...new Set([...parseTerms(m.topics),   ...parseTerms(m.keywords)])].slice(0, 10);

    if (!srcTerms.length && !tgtTerms.length) return null;

    // Βρίσκουμε ποια terms μοιράζονται κοινές λέξεις (>3 chars)
    const connections = [];
    srcTerms.forEach((s, si) => {
        const sWords = new Set(s.toLowerCase().split(/\W+/).filter(w => w.length > 3));
        tgtTerms.forEach((t, ti) => {
            const tWords = new Set(t.toLowerCase().split(/\W+/).filter(w => w.length > 3));
            const shared = [...sWords].filter(w => tWords.has(w));
            if (shared.length) connections.push({ si, ti });
        });
    });

    const connectedSrc = new Set(connections.map(c => c.si));
    const connectedTgt = new Set(connections.map(c => c.ti));

    const ROW_H = 34, PAD_TOP = 20, PAD_SIDE = 16;
    const rows  = Math.max(srcTerms.length, tgtTerms.length);
    const H     = rows * ROW_H + PAD_TOP * 2;
    const W     = 580;
    const LX    = 180, RX = W - 180;

    const nodeY = (i, total) => PAD_TOP + i * ROW_H + ROW_H / 2;

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('width', '100%');
    svg.setAttribute('class', 'concept-graph-svg');

    // Edges πρώτα (πίσω από nodes)
    connections.forEach(({ si, ti }) => {
        const line = document.createElementNS(ns, 'line');
        line.setAttribute('x1', LX + PAD_SIDE); line.setAttribute('y1', nodeY(si, srcTerms.length));
        line.setAttribute('x2', RX - PAD_SIDE); line.setAttribute('y2', nodeY(ti, tgtTerms.length));
        line.setAttribute('class', 'cg-edge');
        svg.appendChild(line);
    });

    // Nodes
    const makeNode = (text, cx, cy, type, connected) => {
        const g = document.createElementNS(ns, 'g');
        const isLeft = type === 'src';
        const maxW = 155;
        const rx = 10;

        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', isLeft ? cx - maxW : cx);
        rect.setAttribute('y', cy - 12);
        rect.setAttribute('width', maxW);
        rect.setAttribute('height', 24);
        rect.setAttribute('rx', rx);
        rect.setAttribute('class', `cg-node cg-node-${type}${connected ? ' cg-node-connected' : ''}`);
        g.appendChild(rect);

        const label = document.createElementNS(ns, 'text');
        label.setAttribute('x', isLeft ? cx - maxW / 2 : cx + maxW / 2);
        label.setAttribute('y', cy + 4);
        label.setAttribute('text-anchor', 'middle');
        label.setAttribute('class', 'cg-label');
        const display = text.length > 22 ? text.slice(0, 21) + '…' : text;
        label.textContent = display;
        g.appendChild(label);
        return g;
    };

    srcTerms.forEach((t, i) => svg.appendChild(makeNode(t, LX, nodeY(i, srcTerms.length), 'src', connectedSrc.has(i))));
    tgtTerms.forEach((t, i) => svg.appendChild(makeNode(t, RX, nodeY(i, tgtTerms.length), 'tgt', connectedTgt.has(i))));

    // Center score badge
    const scoreVal = m.score ?? '';
    if (scoreVal !== '') {
        const cx = W / 2, cy = H / 2;
        const badge = document.createElementNS(ns, 'g');
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', cx); circle.setAttribute('cy', cy);
        circle.setAttribute('r', 22);  circle.setAttribute('class', `cg-badge cg-badge-${m.display_color || 'green'}`);
        badge.appendChild(circle);
        const scoreText = document.createElementNS(ns, 'text');
        scoreText.setAttribute('x', cx); scoreText.setAttribute('y', cy - 3);
        scoreText.setAttribute('text-anchor', 'middle'); scoreText.setAttribute('class', 'cg-badge-score');
        scoreText.textContent = scoreVal + '%';
        badge.appendChild(scoreText);
        const matchLabel = document.createElementNS(ns, 'text');
        matchLabel.setAttribute('x', cx); matchLabel.setAttribute('y', cy + 12);
        matchLabel.setAttribute('text-anchor', 'middle'); matchLabel.setAttribute('class', 'cg-badge-label');
        matchLabel.textContent = 'match';
        badge.appendChild(matchLabel);
        svg.appendChild(badge);
    }

    return svg;
}

// Χτίζει τα tag chips από comma-separated string
function buildTags(str) {
    if (!str) return '';
    return str.split(',').map(t => t.trim()).filter(Boolean)
        .map(t => `<span class="artifact-tag">${t}</span>`).join('');
}

// Singleton modal — δημιουργείται μία φορά
function getArtifactModal() {
    let modal = document.getElementById('artifact-modal');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = 'artifact-modal';
    modal.className = 'artifact-modal-overlay hidden';
    modal.innerHTML = `
        <div class="artifact-modal">
            <div class="artifact-modal-header">
                <div class="artifact-modal-titles">
                    <span class="artifact-modal-src-title"></span>
                    <span class="artifact-modal-arrow">→</span>
                    <span class="artifact-modal-tgt-title"></span>
                </div>
                <button class="artifact-modal-close" aria-label="Κλείσιμο">✕</button>
            </div>
            <div class="artifact-modal-body"></div>
        </div>
    `;
    document.body.appendChild(modal);

    const close = () => modal.classList.add('hidden');
    modal.querySelector('.artifact-modal-close').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });

    return modal;
}

function showArtifactModal(result) {
    const src = result.source;
    const m   = result.matches[0];
    const hasMatch = !!m;
    const modal = getArtifactModal();

    modal.querySelector('.artifact-modal-src-title').textContent = src.title || '';
    modal.querySelector('.artifact-modal-tgt-title').textContent = hasMatch ? (m.title || '') : '—';
    modal.querySelector('.artifact-modal-arrow').style.display = hasMatch ? '' : 'none';

    const srcTopics   = buildTags(src.topics);
    const srcKeywords = buildTags(src.keywords);
    const mTopics     = hasMatch ? buildTags(m.topics)   : '';
    const mKeywords   = hasMatch ? buildTags(m.keywords) : '';

    const body = modal.querySelector('.artifact-modal-body');
    body.innerHTML = `
        ${(srcTopics || mTopics) ? `
        <div class="artifact-modal-section">
            <div class="artifact-modal-cols">
                ${srcTopics ? `<div class="artifact-modal-col">
                    <div class="artifact-modal-col-label">Topics — ${src.title}</div>
                    <div class="artifact-tags">${srcTopics}</div>
                </div>` : ''}
                ${mTopics ? `<div class="artifact-modal-col">
                    <div class="artifact-modal-col-label">Topics — ${m.title}</div>
                    <div class="artifact-tags">${mTopics}</div>
                </div>` : ''}
            </div>
        </div>` : ''}
        ${(srcKeywords || mKeywords) ? `
        <div class="artifact-modal-section">
            <div class="artifact-modal-cols">
                ${srcKeywords ? `<div class="artifact-modal-col">
                    <div class="artifact-modal-col-label">Keywords</div>
                    <div class="artifact-tags">${srcKeywords}</div>
                </div>` : ''}
                ${mKeywords ? `<div class="artifact-modal-col">
                    <div class="artifact-modal-col-label">Keywords</div>
                    <div class="artifact-tags">${mKeywords}</div>
                </div>` : ''}
            </div>
        </div>` : ''}
        ${(!srcTopics && !mTopics && !srcKeywords && !mKeywords) ? `
        <p class="artifact-modal-empty">Δεν υπάρχουν διαθέσιμα δεδομένα για αυτό το μάθημα.</p>` : ''}
    `;

    // Concept graph
    if (hasMatch) {
        const graphSection = document.createElement('div');
        graphSection.className = 'artifact-modal-section';
        const graphLabel = document.createElement('div');
        graphLabel.className = 'artifact-modal-col-label';
        graphLabel.textContent = 'Concept Graph';
        graphSection.appendChild(graphLabel);
        const graph = buildConceptGraph(src, m);
        if (graph) graphSection.appendChild(graph);
        body.appendChild(graphSection);
    }

    modal.classList.remove('hidden');
}

// Χτίζει ένα course-row με expand button που δείχνει το knowledge artifact
function buildCourseRow(result, rowNum) {
    const src      = result.source;
    const m        = result.matches[0];
    const hasMatch = !!m;

    const row = document.createElement('div');
    row.className = 'course-row';

    const main = document.createElement('div');
    main.className = 'course-row-main';
    main.innerHTML = `
        <div class="course-cell">
            <span class="cell-title">${src.title}</span>
            <span class="cell-ects">${src.ects} ECTS</span>
        </div>
        <div class="row-divider"></div>
        ${hasMatch ? `
            <div style="display:flex; align-items:center; gap:12px; flex:1; min-width:0;">
                <a class="course-cell course-cell-link" href="${m.syllabus_url}" target="_blank" aria-label="Syllabus: ${m.title}">
                    <span class="cell-title">${m.title}</span>
                    <span class="cell-ects">${m.ects ?? ''} ECTS</span>
                </a>
                <span data-score-span="${rowNum}" style="font-size:18px; font-weight:800; color:var(--${m.display_color}); flex-shrink:0; width:72px; text-align:right;">${m.score}%</span>
            </div>
        ` : `<div style="flex:1;"><span class="no-match-label">Δεν βρέθηκε αντίστοιχο</span></div>`}
        <button class="expand-btn" title="Knowledge Artifact">▾</button>
    `;

    main.querySelector('.expand-btn').addEventListener('click', () => showArtifactModal(result));

    row.appendChild(main);
    return row;
}

function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }

function toggleSupported(btn) {
    const list = btn.nextElementSibling;
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', !expanded);
    list.classList.toggle('hidden', expanded);
}
