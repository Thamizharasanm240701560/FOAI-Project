/**
 * ══════════════════════════════════════════════════════════════
 * AI Power Optimizer — Frontend Logic
 * ══════════════════════════════════════════════════════════════
 * Handles:
 *   - Loading default appliances from API
 *   - Building / managing the appliance table
 *   - Collecting user input and calling /api/optimize
 *   - Rendering results: Gantt schedule, charts, comparison,
 *     explanations, and SA algorithm details
 *
 * Chart library: Chart.js v4 (loaded via CDN in index.html)
 * ══════════════════════════════════════════════════════════════
 */

const API_BASE = '';  // same origin

// ── Chart.js instances (destroyed before re-creation) ──
let batteryChartInstance = null;
let powerChartInstance   = null;
let fitnessChartInstance = null;
let comparisonChartInstance = null;

// ══════════════════════════════════════════
//  PAGE INITIALISATION
// ══════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    loadDefaults();
    setupListeners();
});

function setupListeners() {
    // Battery percentage → update fill bar + available energy
    const battPct  = document.getElementById('batteryPercentage');
    const battCap  = document.getElementById('batteryCapacity');
    if (battPct) battPct.addEventListener('input', updateEnergyDisplay);
    if (battCap) battCap.addEventListener('input', updateEnergyDisplay);

    // Solar toggle
    const solarCb = document.getElementById('solarEnabled');
    if (solarCb) solarCb.addEventListener('change', toggleSolar);

    // Time-slot size change → rebuild solar inputs if visible
    const timeSlotSel = document.getElementById('timeSlot');
    if (timeSlotSel) timeSlotSel.addEventListener('change', () => {
        if (document.getElementById('solarEnabled').checked) buildSolarInputs();
    });
}

function updateEnergyDisplay() {
    const cap = parseFloat(document.getElementById('batteryCapacity').value) || 0;
    const pct = parseFloat(document.getElementById('batteryPercentage').value) || 0;
    const avail = cap * pct / 100;
    document.getElementById('availableEnergy').textContent = `${avail.toFixed(0)} Wh`;
    document.getElementById('batteryFill').style.width = `${Math.min(100, Math.max(0, pct))}%`;
}

// ══════════════════════════════════════════
//  LOAD DEFAULTS
// ══════════════════════════════════════════

async function loadDefaults() {
    try {
        const resp = await fetch(`${API_BASE}/api/default-appliances`);
        if (!resp.ok) throw new Error('Failed to load defaults');
        const data = await resp.json();

        // Populate backup fields from demo scenario
        if (data.demo_scenario && data.demo_scenario.backup) {
            const b = data.demo_scenario.backup;
            setValue('maxPower', b.max_power_watts);
            setValue('batteryCapacity', b.battery_capacity_wh);
            setValue('batteryPercentage', b.battery_percentage);
            setValue('outageDuration', b.outage_duration_hours);
        }

        // Populate appliance table
        if (data.default_appliances) {
            const body = document.getElementById('applianceBody');
            body.innerHTML = '';
            data.default_appliances.forEach(app => addApplianceRow(app));
        }

        updateEnergyDisplay();
    } catch (err) {
        console.error('Error loading defaults:', err);
        // Fallback: add a few rows manually
        addApplianceRow({ name: 'Refrigerator', power_watts: 150, priority: 'VERY_HIGH',
            required_duration_hours: 3, min_duration_hours: 2, max_duration_hours: 4,
            is_essential: true, continuous_operation: false });
        addApplianceRow({ name: 'Wi-Fi Router', power_watts: 10, priority: 'HIGH',
            required_duration_hours: 3, min_duration_hours: 2, max_duration_hours: 4,
            is_essential: true, continuous_operation: true });
        addApplianceRow({ name: 'Fan', power_watts: 75, priority: 'HIGH',
            required_duration_hours: 2, min_duration_hours: 1, max_duration_hours: 4,
            is_essential: false, continuous_operation: false });
    }
}

function setValue(id, val) {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null) el.value = val;
}

// ══════════════════════════════════════════
//  APPLIANCE TABLE MANAGEMENT
// ══════════════════════════════════════════

function addApplianceRow(app) {
    const body = document.getElementById('applianceBody');
    const tr = document.createElement('tr');

    const d = app || {};
    const name  = d.name || '';
    const power = d.power_watts || '';
    const pri   = d.priority || 'MEDIUM';
    const req   = d.required_duration_hours ?? '';
    const minD  = d.min_duration_hours ?? '';
    const maxD  = d.max_duration_hours ?? '';
    const start = d.preferred_start_hour ?? '';
    const end   = d.preferred_end_hour ?? '';
    const ess   = d.is_essential ? 'checked' : '';
    const cont  = d.continuous_operation ? 'checked' : '';

    const priOpts = ['VERY_HIGH','HIGH','MEDIUM','LOW'].map(p =>
        `<option value="${p}" ${p === pri ? 'selected' : ''}>${p.replace('_',' ')}</option>`
    ).join('');

    tr.innerHTML = `
        <td><input type="text" value="${name}" placeholder="Name"></td>
        <td><input type="number" value="${power}" min="1" placeholder="W"></td>
        <td><select>${priOpts}</select></td>
        <td><input type="number" value="${req}" min="0" step="0.5"></td>
        <td><input type="number" value="${minD}" min="0" step="0.5"></td>
        <td><input type="number" value="${maxD}" min="0" step="0.5"></td>
        <td><input type="number" value="${start}" min="0" max="24" step="1" placeholder="—"></td>
        <td><input type="number" value="${end}" min="0" max="24" step="1" placeholder="—"></td>
        <td><input type="checkbox" ${ess}></td>
        <td><input type="checkbox" ${cont}></td>
        <td><button class="btn btn-danger" onclick="this.closest('tr').remove()">✕</button></td>
    `;
    body.appendChild(tr);
}

function collectAppliances() {
    const rows = document.querySelectorAll('#applianceBody tr');
    const appliances = [];
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input, select');
        const name = inputs[0].value.trim();
        if (!name) return;

        appliances.push({
            name: name,
            power_watts:             parseFloat(inputs[1].value) || 0,
            priority:                inputs[2].value,
            required_duration_hours: parseFloat(inputs[3].value) || 0,
            min_duration_hours:      parseFloat(inputs[4].value) || 0,
            max_duration_hours:      parseFloat(inputs[5].value) || null,
            preferred_start_hour:    inputs[6].value ? parseFloat(inputs[6].value) : null,
            preferred_end_hour:      inputs[7].value ? parseFloat(inputs[7].value) : null,
            is_essential:            inputs[8].checked,
            continuous_operation:    inputs[9].checked,
        });
    });
    return appliances;
}

// ══════════════════════════════════════════
//  SOLAR GENERATION
// ══════════════════════════════════════════

function toggleSolar() {
    const enabled = document.getElementById('solarEnabled').checked;
    document.getElementById('solarPanel').style.display = enabled ? 'block' : 'none';
    if (enabled) buildSolarInputs();
}

function buildSolarInputs() {
    const dur = parseFloat(document.getElementById('outageDuration').value) || 4;
    const slotMin = parseInt(document.getElementById('timeSlot').value) || 30;
    const numSlots = Math.max(1, Math.floor(dur * 60 / slotMin));
    const container = document.getElementById('solarInputs');
    container.innerHTML = '';

    for (let i = 0; i < numSlots; i++) {
        const totalMin = 6 * 60 + i * slotMin;
        const h = Math.floor(totalMin / 60);
        const m = totalMin % 60;
        const label = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;

        const div = document.createElement('div');
        div.className = 'solar-input-group';
        div.innerHTML = `
            <label>${label}</label>
            <input type="number" value="0" min="0" step="50" data-solar-slot="${i}">
        `;
        container.appendChild(div);
    }
}

function collectSolarGeneration() {
    const inputs = document.querySelectorAll('[data-solar-slot]');
    if (inputs.length === 0) return null;
    return Array.from(inputs).map(inp => parseFloat(inp.value) || 0);
}

// ══════════════════════════════════════════
//  AGENT WORKFLOW ANIMATION
// ══════════════════════════════════════════

const AGENT_STEPS = ['observe','analyze','search','optimize','evaluate','decide','act'];

function setAgentStep(stepName) {
    document.querySelectorAll('.step').forEach(el => {
        const s = el.getAttribute('data-step');
        el.classList.remove('active','done');
        if (s === stepName) el.classList.add('active');
        else if (AGENT_STEPS.indexOf(s) < AGENT_STEPS.indexOf(stepName)) el.classList.add('done');
    });
}

async function animateAgentSteps() {
    for (const step of AGENT_STEPS) {
        setAgentStep(step);
        await sleep(300);
    }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ══════════════════════════════════════════
//  RUN OPTIMIZATION
// ══════════════════════════════════════════

async function runOptimization() {
    // Collect inputs
    const appliances = collectAppliances();
    if (appliances.length === 0) {
        alert('Please add at least one appliance.');
        return;
    }

    const solarEnabled = document.getElementById('solarEnabled').checked;
    const solarGen = solarEnabled ? collectSolarGeneration() : null;

    const payload = {
        backup: {
            max_power_watts:     parseFloat(document.getElementById('maxPower').value) || 1000,
            battery_capacity_wh: parseFloat(document.getElementById('batteryCapacity').value) || 3000,
            battery_percentage:  parseFloat(document.getElementById('batteryPercentage').value) || 70,
            outage_duration_hours: parseFloat(document.getElementById('outageDuration').value) || 4,
            solar_enabled:       solarEnabled,
            solar_generation:    solarGen,
        },
        appliances: appliances,
        settings: {
            initial_temperature: parseFloat(document.getElementById('initTemp').value) || 1000,
            min_temperature:     parseFloat(document.getElementById('minTemp').value) || 0.1,
            cooling_rate:        parseFloat(document.getElementById('coolingRate').value) || 0.95,
            max_iterations:      parseInt(document.getElementById('maxIter').value) || 10000,
            time_slot_minutes:   parseInt(document.getElementById('timeSlot').value) || 30,
        }
    };

    // Show loading
    document.getElementById('loadingOverlay').style.display = 'block';
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('runBtn').disabled = true;

    // Animate agent workflow
    animateAgentSteps();

    try {
        const resp = await fetch(`${API_BASE}/api/optimize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const result = await resp.json();

        // Mark all agent steps as done
        document.querySelectorAll('.step').forEach(el => {
            el.classList.remove('active');
            el.classList.add('done');
        });

        renderResults(result);

    } catch (err) {
        alert(`Optimization failed: ${err.message}`);
        console.error(err);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
        document.getElementById('runBtn').disabled = false;
    }
}

// ══════════════════════════════════════════
//  RENDER RESULTS
// ══════════════════════════════════════════

function renderResults(r) {
    document.getElementById('resultsSection').style.display = 'block';

    // Summary stats
    document.getElementById('statFitness').textContent   = r.fitness.toFixed(1);
    document.getElementById('statEnergy').textContent     = `${r.energy_consumed_wh.toFixed(0)} Wh`;
    document.getElementById('statRemaining').textContent  = `${r.remaining_energy_wh.toFixed(0)} Wh`;
    document.getElementById('statBattery').textContent    = `${r.battery_percentage.toFixed(1)}%`;
    document.getElementById('statPeak').textContent       = `${r.peak_power_watts.toFixed(0)} W`;
    document.getElementById('statPriority').textContent   = `${r.priority_satisfaction}%`;
    document.getElementById('statEssential').textContent  = `${r.essential_satisfaction}%`;
    document.getElementById('statPowered').textContent    = `${r.appliances_powered}/${r.total_appliances}`;

    // Warnings
    const warningsSection = document.getElementById('warningsSection');
    const warningsList = document.getElementById('warningsList');
    if (r.warnings && r.warnings.length > 0) {
        warningsSection.style.display = 'block';
        warningsList.innerHTML = r.warnings.map(w =>
            `<div class="warning-item">${w}</div>`
        ).join('');
    } else {
        warningsSection.style.display = 'none';
    }

    // Gantt schedule
    renderGantt(r);

    // Charts
    renderBatteryChart(r);
    renderPowerChart(r);

    // Comparison
    renderComparison(r);

    // Explanations
    renderExplanations(r);

    // Algorithm details
    renderAlgorithmDetails(r);

    // Scroll to results
    document.getElementById('summaryCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ══════════════════════════════════════════
//  GANTT SCHEDULE
// ══════════════════════════════════════════

function renderGantt(r) {
    const container = document.getElementById('ganttContainer');
    const slots = r.time_slots;

    let html = '<table class="gantt-table"><thead><tr><th>Appliance</th>';
    slots.forEach(s => { html += `<th>${s}</th>`; });
    html += '</tr></thead><tbody>';

    r.schedule.forEach(app => {
        html += '<tr>';
        html += `<td class="app-name">
            ${app.appliance_name}
            <br><span class="gantt-power">${app.power_watts}W</span>
            ${app.is_essential ? '<br><span class="gantt-essential">★ Essential</span>' : ''}
        </td>`;
        app.slots.forEach(val => {
            if (val === 1) {
                html += '<td><div class="gantt-on">ON</div></td>';
            } else {
                html += '<td><div class="gantt-off">OFF</div></td>';
            }
        });
        html += '</tr>';
    });

    // Power total row
    html += '<tr><td class="app-name" style="color:var(--accent-cyan);">Total Power</td>';
    r.power_per_slot.forEach(p => {
        const maxP = parseFloat(document.getElementById('maxPower').value) || 1000;
        const over = p > maxP;
        html += `<td style="color:${over ? 'var(--accent-red)' : 'var(--accent-cyan)'}; font-weight:600; font-size:0.75rem;">${p}W</td>`;
    });
    html += '</tr>';

    html += '</tbody></table>';
    container.innerHTML = html;
}

// ══════════════════════════════════════════
//  BATTERY CHART
// ══════════════════════════════════════════

function renderBatteryChart(r) {
    const ctx = document.getElementById('batteryChart').getContext('2d');
    if (batteryChartInstance) batteryChartInstance.destroy();

    batteryChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: r.time_slots,
            datasets: [{
                label: 'Battery %',
                data: r.battery_percentage_per_slot,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 3,
                pointBackgroundColor: '#10b981',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { family: 'Inter' } } },
            },
            scales: {
                y: {
                    min: 0, max: 100,
                    title: { display: true, text: 'Battery %', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                x: {
                    title: { display: true, text: 'Time', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                }
            }
        }
    });
}

// ══════════════════════════════════════════
//  POWER USAGE CHART
// ══════════════════════════════════════════

function renderPowerChart(r) {
    const ctx = document.getElementById('powerChart').getContext('2d');
    if (powerChartInstance) powerChartInstance.destroy();

    const maxP = parseFloat(document.getElementById('maxPower').value) || 1000;
    const maxLine = r.power_per_slot.map(() => maxP);

    powerChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: r.time_slots,
            datasets: [
                {
                    label: 'Power Usage (W)',
                    data: r.power_per_slot,
                    backgroundColor: r.power_per_slot.map(p =>
                        p > maxP ? 'rgba(239, 68, 68, 0.6)' : 'rgba(59, 130, 246, 0.6)'
                    ),
                    borderColor: r.power_per_slot.map(p =>
                        p > maxP ? '#ef4444' : '#3b82f6'
                    ),
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'Inverter Max (W)',
                    data: maxLine,
                    type: 'line',
                    borderColor: '#ef4444',
                    borderDash: [6, 4],
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { family: 'Inter' } } },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Watts', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                x: {
                    title: { display: true, text: 'Time', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                }
            }
        }
    });
}

// ══════════════════════════════════════════
//  BEFORE vs AFTER COMPARISON
// ══════════════════════════════════════════

function renderComparison(r) {
    const c = r.comparison;

    // Naive stats
    const naiveDiv = document.getElementById('naiveStats');
    naiveDiv.innerHTML = comparisonStatHTML('Energy Consumed', `${c.naive_energy_consumed.toFixed(0)} Wh`)
        + comparisonStatHTML('Remaining Energy', `${c.naive_remaining_energy.toFixed(0)} Wh`)
        + comparisonStatHTML('Priority Score', `${c.naive_priority_score}%`)
        + comparisonStatHTML('Essential Satisfaction', `${c.naive_essential_satisfaction}%`)
        + comparisonStatHTML('Appliances Powered', c.naive_appliances_powered)
        + comparisonStatHTML('Backup Duration', `${c.naive_backup_duration}h`);

    // SA stats
    const saDiv = document.getElementById('saStats');
    saDiv.innerHTML = comparisonStatHTML('Energy Consumed', `${c.sa_energy_consumed.toFixed(0)} Wh`)
        + comparisonStatHTML('Remaining Energy', `${c.sa_remaining_energy.toFixed(0)} Wh`)
        + comparisonStatHTML('Priority Score', `${c.sa_priority_score}%`)
        + comparisonStatHTML('Essential Satisfaction', `${c.sa_essential_satisfaction}%`)
        + comparisonStatHTML('Appliances Powered', c.sa_appliances_powered)
        + comparisonStatHTML('Backup Duration', `${c.sa_backup_duration}h`);

    // Comparison bar chart
    const ctx = document.getElementById('comparisonChart').getContext('2d');
    if (comparisonChartInstance) comparisonChartInstance.destroy();

    comparisonChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Priority Score', 'Essential Sat.', 'Appliances', 'Backup (h)'],
            datasets: [
                {
                    label: 'Naive',
                    data: [c.naive_priority_score, c.naive_essential_satisfaction, c.naive_appliances_powered * 10, c.naive_backup_duration * 10],
                    backgroundColor: 'rgba(245, 158, 11, 0.5)',
                    borderColor: '#f59e0b',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'SA Optimized',
                    data: [c.sa_priority_score, c.sa_essential_satisfaction, c.sa_appliances_powered * 10, c.sa_backup_duration * 10],
                    backgroundColor: 'rgba(16, 185, 129, 0.5)',
                    borderColor: '#10b981',
                    borderWidth: 1,
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { family: 'Inter' } } },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                x: {
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                }
            }
        }
    });
}

function comparisonStatHTML(label, value) {
    return `<div class="comparison-stat">
        <span class="comparison-stat-label">${label}</span>
        <span class="comparison-stat-value">${value}</span>
    </div>`;
}

// ══════════════════════════════════════════
//  EXPLANATIONS
// ══════════════════════════════════════════

function renderExplanations(r) {
    const container = document.getElementById('explanationList');
    container.innerHTML = r.explanations.map(exp =>
        `<div class="explanation-item">${exp}</div>`
    ).join('');
}

// ══════════════════════════════════════════
//  ALGORITHM DETAILS  (SA Telemetry)
// ══════════════════════════════════════════

function renderAlgorithmDetails(r) {
    const m = r.sa_metrics;
    const total = m.accepted_count + m.rejected_count;
    const rate  = total > 0 ? ((m.accepted_count / total) * 100).toFixed(1) : '0';

    document.getElementById('algoInitTemp').textContent    = m.initial_temperature.toFixed(1);
    document.getElementById('algoFinalTemp').textContent   = m.final_temperature.toFixed(4);
    document.getElementById('algoIterations').textContent  = m.total_iterations.toLocaleString();
    document.getElementById('algoInitFitness').textContent = m.initial_fitness.toFixed(1);
    document.getElementById('algoBestFitness').textContent = m.best_fitness.toFixed(1);
    document.getElementById('algoAccepted').textContent    = m.accepted_count.toLocaleString();
    document.getElementById('algoRejected').textContent    = m.rejected_count.toLocaleString();
    document.getElementById('algoAcceptRate').textContent   = `${rate}%`;

    // Fitness-vs-Iteration chart
    const ctx = document.getElementById('fitnessChart').getContext('2d');
    if (fitnessChartInstance) fitnessChartInstance.destroy();

    const iterLabels = m.fitness_history.map((_, i) => {
        const iterNum = Math.round(i * (m.total_iterations / m.fitness_history.length));
        return iterNum;
    });

    fitnessChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: iterLabels,
            datasets: [
                {
                    label: 'Best Fitness',
                    data: m.fitness_history,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 0,
                },
                {
                    label: 'Temperature',
                    data: m.temperature_history,
                    borderColor: '#ef4444',
                    borderDash: [4, 3],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    yAxisID: 'y1',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { family: 'Inter' } } },
                title: {
                    display: true,
                    text: 'Simulated Annealing Convergence',
                    color: '#94a3b8',
                    font: { family: 'Inter', size: 14 },
                }
            },
            scales: {
                y: {
                    title: { display: true, text: 'Fitness', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y1: {
                    position: 'right',
                    title: { display: true, text: 'Temperature', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { drawOnChartArea: false },
                },
                x: {
                    title: { display: true, text: 'Iteration', color: '#94a3b8' },
                    ticks: { color: '#64748b', maxTicksLimit: 10 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                }
            }
        }
    });
}
