document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const uploadPanel = document.getElementById('upload-panel');
    const resultPanel = document.getElementById('result-panel');
    const loader = document.getElementById('loader');
    const resultImage = document.getElementById('result-image');
    const btnBack = document.getElementById('btn-back');
    const btnDownload = document.getElementById('btn-download');

    let currentFileUrl = null;

    // Trigger file selection on click
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });

    // Drag and drop styles
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });

    btnBack.addEventListener('click', () => {
        if (currentFileUrl) {
            URL.revokeObjectURL(currentFileUrl);
            currentFileUrl = null;
        }
        resultPanel.style.display = 'none';
        uploadPanel.style.display = 'block';
        dropzone.style.display = 'block';
        loader.style.display = 'none';
        fileInput.value = '';
    });

    async function handleFile(file) {
        if (!file.type.startsWith('image/')) {
            alert('请上传图片文件 (JPG / PNG / HEIC)');
            return;
        }

        // 统一 Loader 管理：确保任何错误都能关闭它
        const setLoader = (show, text = "正在生成高品质水印...") => {
            loader.style.display = show ? 'block' : 'none';
            if (show) loader.querySelector('p').innerText = text;
            dropzone.style.display = show ? 'none' : 'block';
        };

        setLoader(true, "正在智能分析照片 EXIF...");

        try {
            // 1. 容错提取 EXIF (优先前端，失败则使用静默默认值)
            let tags = {};
            if (typeof exifr !== 'undefined') {
                try { tags = await exifr.parse(file, true) || {}; } catch (e) { console.warn("EXIF 解析失败"); }
            }
            
            const device = tags.Model ? (tags.Make && !tags.Model.includes(tags.Make) ? `${tags.Make} ${tags.Model}` : tags.Model) : "iPhone";
            
            let p = [];
            if (tags.FocalLengthIn35mmFormat || tags.FocalLength) p.push((tags.FocalLengthIn35mmFormat || tags.FocalLength) + "mm");
            if (tags.FNumber) p.push("f/" + tags.FNumber);
            if (tags.ExposureTime) p.push(tags.ExposureTime > 1 ? tags.ExposureTime + "s" : "1/" + Math.round(1/tags.ExposureTime) + "s");
            if (tags.ISO) p.push("ISO" + tags.ISO);
            const params = p.join("  ") || "48MP Pro Fusion System";
            
            const dt = tags.DateTimeOriginal || new Date();
            const dateStr = dt instanceof Date ? `${dt.getFullYear()}.${dt.getMonth()+1}.${dt.getDate()} ${dt.getHours()}:${String(dt.getMinutes()).padStart(2, '0')}` : "2026.04.05 22:00";
            
            // 2. 准备底座拼合 (Canvas)
            setLoader(true, "正在智能分析原片画幅...");
            const originalImg = new Image();
            const fileUrl = URL.createObjectURL(file);
            
            await new Promise((resolve, reject) => {
                originalImg.onload = () => {
                    resolve();
                };
                originalImg.onerror = () => {
                    URL.revokeObjectURL(fileUrl);
                    reject(new Error("原片无法解析，请确保是标准的相册照片"));
                };
                originalImg.src = fileUrl;
            });

            // 生成缩略图算直方图
            const tC = document.createElement('canvas');
            tC.width = 120; tC.height = 120;
            const tCtx = tC.getContext('2d');
            tCtx.drawImage(originalImg, 0, 0, 120, 120);
            const thumbB64 = tC.toDataURL('image/jpeg', 0.6);
            URL.revokeObjectURL(fileUrl); // 加载完缩略图即可释放原始内存指针

            // 3. 通信后端：获取 SVG 模板
            setLoader(true, "正在云端渲染矢量艺术模版...");
            const fd = new FormData();
            fd.append('device', device);
            fd.append('params', params);
            fd.append('date_str', dateStr);
            fd.append('thumb_b64', thumbB64);
            fd.append('theme', 'light'); // Demo 默认 Light 后续可加自动亮度探测
            
            if (tags.latitude && tags.longitude) {
                fd.append('lat', tags.latitude);
                fd.append('lon', tags.longitude);
            }
            
            const locValue = document.getElementById('location-input').value.trim();
            if (locValue) fd.append('location', locValue);

            const resp = await fetch('/v1/watermark/svg', { method: 'POST', body: fd });
            if (!resp.ok) throw new Error("服务器生成模版失败，请稍后重试");
            const svgText = await resp.text();

            // 4. 极致合成：采用双重加载守卫
            setLoader(true, "正在完成最后的细节光刻...");
            const wmRatio = (originalImg.width / originalImg.height) > 1.0 ? 0.085 : 0.115;
            const wmH = Math.ceil(originalImg.width * wmRatio);
            
            const canvas = document.createElement('canvas');
            canvas.width = originalImg.width;
            canvas.height = originalImg.height + wmH;
            const ctx = canvas.getContext('2d');
            
            // 下方涂白底漆
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, originalImg.height, canvas.width, wmH);
            ctx.drawImage(originalImg, 0, 0);

            // 加载并绘制 SVG
            const svgImg = new Image();
            const svgUrl = URL.createObjectURL(new Blob([svgText], {type: 'image/svg+xml;charset=utf-8'}));
            
            await new Promise((resolve, reject) => {
                svgImg.onload = () => {
                    ctx.drawImage(svgImg, 0, originalImg.height, canvas.width, wmH);
                    URL.revokeObjectURL(svgUrl);
                    resolve();
                };
                svgImg.onerror = () => {
                    URL.revokeObjectURL(svgUrl);
                    reject(new Error("SVG 渲染超时或签名素材异常"));
                };
                svgImg.src = svgUrl;
            });

            // 最终输出
            canvas.toBlob(blob => {
                if (currentFileUrl) URL.revokeObjectURL(currentFileUrl);
                currentFileUrl = URL.createObjectURL(blob);
                resultImage.src = currentFileUrl;
                
                btnDownload.onclick = () => {
                    const a = document.createElement('a');
                    a.href = currentFileUrl;
                    a.download = `Shot_on_iOS_${Date.now()}.jpg`;
                    a.click();
                };

                uploadPanel.style.display = 'none';
                resultPanel.style.display = 'block';
                setLoader(false);
                URL.revokeObjectURL(fileUrl);
            }, 'image/jpeg', 0.95);

        } catch (error) {
            console.error('合成失败:', error);
            alert('生成失败: ' + error.message);
            setLoader(false);
        }
    }
});
