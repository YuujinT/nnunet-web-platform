/**
 * nnU-Net Web Platform 主应用
 * 直接移植工作版本的代码逻辑
 */

const API_BASE = '';
let appInstance = null;

class NNUnetWebApp {
    constructor() {
        this.nv = null;
        this.currentCase = null;
        this.currentMode = 'both';
        this.uploadFiles = null;
        this.pollIntervals = new Map();

        this.init();
    }

    async init() {
        try {
            await this.initNiivue();
            this.initEventListeners();
            await this.loadCases();
            await this.loadModels();
            this.logInfo('初始化完成');
        } catch (e) {
            this.logError('初始化失败', e);
        }
    }

    async initNiivue() {
        try {
            if (typeof niivue === 'undefined') {
                throw new Error('Niivue 库未加载');
            }

            this.nv = new niivue.Niivue({
                show3Dcrosshair: true,
                backColor: [0, 0, 0, 1],
                crosshairColor: [1, 1, 1, 0.5],
            });

            await this.nv.attachTo('gl');
            this.logInfo('Niivue 初始化成功');
        } catch (e) {
            this.logError('Niivue 初始化失败', e);
            throw e;
        }
    }

    initEventListeners() {
        // 透明度滑块 - 直接移植工作版本的代码
        const opacitySlider = document.getElementById('opacity');
        if (opacitySlider) {
            opacitySlider.addEventListener('input', (e) => {
                if (this.nv && this.nv.volumes) {
                    const opacity = e.target.value / 100;
                    const opacityValue = document.getElementById('opacityValue');
                    if (opacityValue) opacityValue.textContent = `${e.target.value}%`;

                    // 直接移植工作版本：更新所有 overlay 的透明度（跳过背景）
                    for (let i = 1; i < this.nv.volumes.length; i++) {
                        if (this.nv.volumes[i]) {
                            this.nv.volumes[i].opacity = opacity;
                        }
                    }
                    this.nv.updateGLVolume();
                    this.logInfo(`更新透明度: ${opacity * 100}%`);
                }
            });
        }

        // 病例选择
        const caseSelect = document.getElementById('caseSelect');
        if (caseSelect) {
            caseSelect.addEventListener('change', async (e) => {
                const caseId = e.target.value;
                if (caseId) {
                    await this.loadCase(caseId);
                    const inferencePanel = document.getElementById('inferencePanel');
                    if (inferencePanel) inferencePanel.style.display = 'block';
                } else {
                    this.clearViewer();
                    const caseInfo = document.getElementById('caseInfo');
                    if (caseInfo) caseInfo.innerHTML = '<p class="empty-text">请选择或上传病例</p>';
                    const inferencePanel = document.getElementById('inferencePanel');
                    if (inferencePanel) inferencePanel.style.display = 'none';
                    const emptyState = document.getElementById('emptyState');
                    if (emptyState) emptyState.style.display = 'flex';
                }
            });
        }

        // 上传区域
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        if (dropZone && fileInput) {
            dropZone.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => {
                this.handleFileSelection(e.target.files);
            });
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });
            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('dragover');
            });
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                this.handleFileSelection(e.dataTransfer.files);
            });
        }
    }

    handleFileSelection(files) {
        const fileList = document.getElementById('fileList');
        const uploadBtn = document.getElementById('uploadBtn');
        if (!fileList || !uploadBtn) return;

        fileList.innerHTML = '';
        if (files.length === 0) {
            uploadBtn.disabled = true;
            return;
        }

        Array.from(files).forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span class="file-name">${file.name}</span>
                <span class="file-size">${this.formatFileSize(file.size)}</span>
            `;
            fileList.appendChild(fileItem);
        });

        uploadBtn.disabled = false;
        this.uploadFiles = files;
    }

    async loadCases() {
        try {
            const response = await fetch(`${API_BASE}/api/cases`);
            if (!response.ok) throw new Error(`HTTP 错误: ${response.status}`);

            const cases = await response.json();
            const caseSelect = document.getElementById('caseSelect');
            if (!caseSelect) return;

            caseSelect.innerHTML = '<option value="">选择病例...</option>';

            if (cases.length > 0) {
                cases.forEach(caseItem => {
                    const option = document.createElement('option');
                    option.value = caseItem.id || caseItem.case_id;
                    option.textContent = caseItem.case_name || caseItem.name || caseItem.id;
                    caseSelect.appendChild(option);
                });
                this.logInfo(`加载 ${cases.length} 个病例`);
            }
        } catch (e) {
            this.logError('加载病例失败', e);
        }
    }

    async loadModels() {
        try {
            const response = await fetch(`${API_BASE}/api/models`);
            if (!response.ok) return;

            const models = await response.json();
            const modelSelect = document.getElementById('modelSelect');
            if (!modelSelect) return;

            modelSelect.innerHTML = '';
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;
                option.textContent = model.display_name || model.name;
                modelSelect.appendChild(option);
            });
        } catch (e) {
            this.logError('加载模型失败', e);
        }
    }

    // ========== 直接移植工作版本的 loadCase ==========
    async loadCase(caseId) {
        if (!caseId) return;

        this.showLoading('加载病例数据...', true);
        this.currentCase = caseId;

        try {
            const response = await fetch(`${API_BASE}/api/cases/${caseId}`);
            const caseData = await response.json();
            this.logInfo(`获取病例数据成功`);

            this.updateCaseInfo(caseData);

            // 关键：先移除所有已加载的 volumes - 直接移植工作版本
            while (this.nv.volumes && this.nv.volumes.length > 0) {
                this.nv.removeVolume(this.nv.volumes[0]);
            }

            const emptyState = document.getElementById('emptyState');
            if (emptyState) emptyState.style.display = 'none';

            const baseUrl = window.location.origin;
            const volumes = [];

            // 主影像 - 总是加载
            if (caseData.imaging_path) {
                volumes.push({
                    url: `${baseUrl}${API_BASE}${caseData.imaging_path}`,
                    name: 'imaging.nii.gz',
                    colormap: 'gray',
                    opacity: 1.0
                });
            }

            // 根据当前模式添加预测和金标准 - 直接移植工作版本的逻辑
            if (this.currentMode === 'both') {
                if (caseData.has_prediction && caseData.prediction_path) {
                    volumes.push({
                        url: `${baseUrl}${API_BASE}${caseData.prediction_path}`,
                        name: 'prediction.nii.gz',
                        colormap: 'red',
                        opacity: 0.5
                    });
                }
                if (caseData.has_ground_truth && caseData.ground_truth_path) {
                    volumes.push({
                        url: `${baseUrl}${API_BASE}${caseData.ground_truth_path}`,
                        name: 'segmentation.nii.gz',
                        colormap: 'green',
                        opacity: 0.3
                    });
                }
            } else if (this.currentMode === 'pred') {
                if (caseData.has_prediction && caseData.prediction_path) {
                    volumes.push({
                        url: `${baseUrl}${API_BASE}${caseData.prediction_path}`,
                        name: 'prediction.nii.gz',
                        colormap: 'red',
                        opacity: 0.7
                    });
                }
            } else if (this.currentMode === 'gt') {
                if (caseData.has_ground_truth && caseData.ground_truth_path) {
                    volumes.push({
                        url: `${baseUrl}${API_BASE}${caseData.ground_truth_path}`,
                        name: 'segmentation.nii.gz',
                        colormap: 'green',
                        opacity: 0.7
                    });
                }
            }

            if (volumes.length > 0) {
                this.logInfo(`加载 ${volumes.length} 个文件`);
                await this.nv.loadVolumes(volumes);
                this.logInfo('loadVolumes 成功');

                // 设置多平面视图
                this.nv.setSliceType(this.nv.sliceTypeMultiplanar);

                // 更新滑块状态 - 直接移植工作版本
                const slider = document.getElementById('opacity');
                if (slider && this.nv.volumes.length > 1 && this.nv.volumes[1]) {
                    slider.disabled = false;
                    slider.value = this.nv.volumes[1].opacity * 100;
                    const opacityValue = document.getElementById('opacityValue');
                    if (opacityValue) opacityValue.textContent = `${slider.value}%`;
                }
            }

            const currentModeEl = document.getElementById('currentMode');
            if (currentModeEl) currentModeEl.textContent = this.getModeText(this.currentMode);

            this.hideLoading();
            this.logInfo(`病例 ${caseId} 加载完成`);

        } catch (e) {
            this.logError('加载病例失败', e);
            this.hideLoading();
        }
    }

    // ========== 直接移植工作版本的 setMode ==========
    setMode(mode) {
        if (!['both', 'pred', 'gt'].includes(mode)) return;
        this.currentMode = mode;

        // 更新按钮状态
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });

        const currentModeEl = document.getElementById('currentMode');
        if (currentModeEl) currentModeEl.textContent = this.getModeText(mode);

        // 重新加载当前病例
        if (this.currentCase) {
            this.loadCase(this.currentCase);
        }
    }

    async confirmUpload() {
        if (!this.uploadFiles || this.uploadFiles.length === 0) {
            this.showNotification('请选择要上传的文件', 'warning');
            return;
        }

        this.showLoading('上传中...', true);
        const hasGroundTruth = document.getElementById('hasGroundTruth')?.checked || false;
        const formData = new FormData();

        try {
            Array.from(this.uploadFiles).forEach(file => {
                formData.append('files', file);
            });
            formData.append('has_ground_truth', hasGroundTruth);

            const res = await fetch(`${API_BASE}/api/cases/upload`, {
                method: 'POST',
                body: formData
            });

            const data = await res.json();

            if (data.success) {
                this.showNotification('上传成功', 'success');
                await this.loadCases();

                const caseSelect = document.getElementById('caseSelect');
                if (caseSelect && data.case_id) {
                    caseSelect.value = data.case_id;
                }

                if (data.case_id) {
                    this.currentCase = data.case_id;
                    const inferencePanel = document.getElementById('inferencePanel');
                    if (inferencePanel) inferencePanel.style.display = 'block';
                    await this.loadCase(data.case_id);
                }

                hideUploadModal();
            } else {
                throw new Error(data.message || '上传失败');
            }
        } catch (e) {
            this.logError('上传失败', e);
            this.showNotification(`上传失败: ${e.message}`, 'error');
        } finally {
            this.hideLoading();
            this.uploadFiles = null;
            const fileList = document.getElementById('fileList');
            const uploadBtn = document.getElementById('uploadBtn');
            if (fileList) fileList.innerHTML = '';
            if (uploadBtn) uploadBtn.disabled = true;
        }
    }

    async startInference() {
        if (!this.currentCase) {
            this.showNotification('请先选择病例', 'warning');
            return;
        }

        const modelSelect = document.getElementById('modelSelect');
        const foldSelect = document.getElementById('foldSelect');
        const modelConfigSelect = document.getElementById('modelConfigSelect');

        const modelName = modelSelect?.value;
        const foldRaw = (foldSelect?.value || '').trim();
        const fold = foldRaw === '' ? null : parseInt(foldRaw, 10);
        const modelConfigRaw = (modelConfigSelect?.value || '').trim().toLowerCase();
        const modelConfig = ['3d_fullres', '3d_lowres'].includes(modelConfigRaw) ? modelConfigRaw : null;

        if (!modelName) {
            this.showNotification('请选择推理模型', 'warning');
            return;
        }

        if (!modelConfig) {
            this.showNotification('模型属性无效，请刷新页面后重试', 'warning');
            this.logError('模型属性未正确读取', { modelConfigRaw });
            return;
        }

        const taskModal = document.getElementById('taskModal');
        if (taskModal) taskModal.classList.add('active');

        this.updateTaskProgress(0, '启动推理任务...', '任务初始化中');

        try {
            const payload = {
                case_id: this.currentCase,
                model_name: modelName,
                fold,
                model_variant: modelConfig,
            };
            this.logInfo(`推理请求参数: ${JSON.stringify(payload)}`);

            const res = await fetch(`${API_BASE}/api/inference/start`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            const data = await res.json();

            if (data.task_id) {
                this.logInfo(`推理任务启动: ${data.task_id}`);
                this.pollTaskStatus(data.task_id, this.currentCase);
            } else {
                throw new Error(data.message || '推理任务启动失败');
            }
        } catch (e) {
            this.logError('推理启动失败', e);
            this.showNotification(`推理启动失败: ${e.message}`, 'error');
            if (taskModal) taskModal.classList.remove('active');
        }
    }

    pollTaskStatus(taskId, caseId) {
        if (this.pollIntervals.has(taskId)) {
            this.clearPoll(taskId);
        }

        const poll = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/inference/status/${taskId}`);
                const status = await res.json();

                this.updateTaskProgress(
                    status.progress || 0,
                    status.message || '处理中...',
                    status.detail || ''
                );

                if (status.status === 'completed') {
                    this.showNotification('推理完成！', 'success');
                    await this.loadCase(caseId);
                    const taskModal = document.getElementById('taskModal');
                    if (taskModal) taskModal.classList.remove('active');
                    this.logInfo(`推理任务完成: ${taskId}`);
                    this.clearPoll(taskId);
                } else if (status.status === 'failed') {
                    throw new Error(status.error || status.message || '推理失败');
                } else {
                    const timeoutId = setTimeout(poll, 1000);
                    this.pollIntervals.set(taskId, timeoutId);
                }
            } catch (e) {
                this.logError('推理任务失败', e);
                this.clearPoll(taskId);
            }
        };

        poll();
    }

    clearPoll(taskId) {
        const timeoutId = this.pollIntervals.get(taskId);
        if (timeoutId) {
            clearTimeout(timeoutId);
            this.pollIntervals.delete(taskId);
        }
    }

    showLoading(text = '加载中...', showProgress = false) {
        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        const progressBar = document.getElementById('progressBar');
        const loadingDetail = document.getElementById('loadingDetail');

        if (overlay) overlay.style.display = 'flex';
        if (loadingText) loadingText.textContent = text;
        if (loadingDetail) loadingDetail.textContent = '准备中';
        if (progressBar) {
            progressBar.style.width = showProgress ? '0%' : '100%';
            progressBar.style.display = showProgress ? 'block' : 'none';
        }
    }

    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    updateTaskProgress(progress, message, detail) {
        const progressBar = document.getElementById('taskProgressBar');
        const taskMessage = document.getElementById('taskMessage');
        const taskDetail = document.getElementById('taskDetail');

        if (progressBar) progressBar.style.width = `${progress}%`;
        if (taskMessage) taskMessage.textContent = message;
        if (taskDetail) taskDetail.textContent = detail || '';
    }

    showNotification(message, type) {
        try {
            const level = type || 'info';
            if (level === 'error') {
                this.logError(message);
            } else if (level === 'warning') {
                this.addDebugLog(`[WARNING] ${new Date().toLocaleTimeString()} - ${message}`, 'warning');
            } else {
                this.logInfo(`${level.toUpperCase()}: ${message}`);
            }

            const notification = document.createElement('div');
            notification.className = `notification ${type || 'info'}`;
            notification.textContent = message;

            const colors = {
                success: '#4CAF50',
                error: '#f44336',
                warning: '#ff9800',
                info: '#2196F3'
            };

            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 20px;
                border-radius: 4px;
                color: white;
                z-index: 9999;
                opacity: 0;
                transition: opacity 0.3s;
                background: ${colors[type || 'info']};
                max-width: 300px;
                word-wrap: break-word;
            `;

            document.body.appendChild(notification);
            setTimeout(() => { notification.style.opacity = '1'; }, 10);
            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        } catch (e) {
            console.error(message);
        }
    }

    logInfo(message) {
        this.addDebugLog(`[INFO] ${new Date().toLocaleTimeString()} - ${message}`, 'info');
    }

    logError(message, error) {
        const errorMsg = error ? `${message}: ${error.message || error}` : message;
        this.addDebugLog(`[ERROR] ${new Date().toLocaleTimeString()} - ${errorMsg}`, 'error');
    }

    addDebugLog(message, level = 'info') {
        const debugContent = document.getElementById('debugContent');
        if (debugContent) {
            const logItem = document.createElement('div');
            logItem.className = 'log-item';
            logItem.textContent = message;
            debugContent.appendChild(logItem);
            debugContent.scrollTop = debugContent.scrollHeight;
        }

        // 浏览器 console 仅输出 warning/error
        if (level === 'error') {
            console.error(message);
        } else if (level === 'warning') {
            console.warn(message);
        }
    }

    updateCaseInfo(caseData) {
        const caseInfo = document.getElementById('caseInfo');
        if (!caseInfo) return;

        const caseId = caseData.case_id || caseData.id || '未知';
        const caseName = caseData.case_name || caseData.name || '未命名';
        const uploadTime = caseData.upload_time || '未知';
        const hasPrediction = caseData.has_prediction || false;
        const hasGroundTruth = caseData.has_ground_truth || false;

        caseInfo.innerHTML = `
            <div class="case-info-item"><span class="label">病例ID:</span><span class="value">${caseId}</span></div>
            <div class="case-info-item"><span class="label">病例名称:</span><span class="value">${caseName}</span></div>
            <div class="case-info-item"><span class="label">上传时间:</span><span class="value">${uploadTime}</span></div>
            <div class="case-info-item"><span class="label">推理状态:</span><span class="value ${hasPrediction ? 'success' : 'warning'}">${hasPrediction ? '已完成' : '未推理'}</span></div>
            <div class="case-info-item"><span class="label">金标准:</span><span class="value ${hasGroundTruth ? 'success' : 'warning'}">${hasGroundTruth ? '已上传' : '未上传'}</span></div>
        `;
    }

    async clearViewer() {
        if (!this.nv) return;

        try {
            while (this.nv.volumes && this.nv.volumes.length > 0) {
                this.nv.removeVolume(this.nv.volumes[0]);
            }
        } catch (error) {
            this.logError('清理查看器失败', error);
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    getModeText(mode) {
        const map = {'both': '对比模式', 'pred': '仅预测', 'gt': '仅金标准'};
        return map[mode] || mode;
    }
}

// 全局函数
function showUploadModal() {
    const modal = document.getElementById('uploadModal');
    if (modal) modal.classList.add('active');
    const fileList = document.getElementById('fileList');
    const uploadBtn = document.getElementById('uploadBtn');
    const hasGroundTruth = document.getElementById('hasGroundTruth');
    if (fileList) fileList.innerHTML = '';
    if (uploadBtn) uploadBtn.disabled = true;
    if (hasGroundTruth) hasGroundTruth.checked = false;
}

function hideUploadModal() {
    const modal = document.getElementById('uploadModal');
    if (modal) modal.classList.remove('active');
}

function confirmUpload() { if (appInstance) appInstance.confirmUpload(); }
function setMode(mode) { if (appInstance) appInstance.setMode(mode); }
function startInference() { if (appInstance) appInstance.startInference(); }
function cancelOperation() {
    if (!appInstance) return;
    appInstance.hideLoading();
    const taskModal = document.getElementById('taskModal');
    if (taskModal) taskModal.classList.remove('active');
}
function toggleDebug(event) {
    if (event) event.stopPropagation();
    const panel = document.getElementById('debugPanel');
    const btn = document.getElementById('toggleDebugBtn');
    if (!panel || !btn) return;

    panel.classList.toggle('collapsed');
    btn.textContent = panel.classList.contains('collapsed') ? '展开' : '收起';
}
function clearDebug(event) {
    if (event) event.stopPropagation();
    const debugContent = document.getElementById('debugContent');
    if (!debugContent) return;
    debugContent.innerHTML = '';
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    appInstance = new NNUnetWebApp();
    window.app = appInstance;
});