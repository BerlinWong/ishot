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
            alert('请上传图片文件 (JPG / PNG)');
            return;
        }

        // Show UI loading
        dropzone.style.display = 'none';
        loader.style.display = 'block';

        const formData = new FormData();
        formData.append('file', file);
        
        const locValue = document.getElementById('location-input').value.trim();
        if (locValue) {
            formData.append('location', locValue);
        }

        try {
            const response = await fetch('/v1/watermark', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || '处理出错');
            }

            const blob = await response.blob();
            currentFileUrl = URL.createObjectURL(blob);
            resultImage.src = currentFileUrl;
            
            // Reconfigure download button
            btnDownload.onclick = () => {
                const a = document.createElement('a');
                a.href = currentFileUrl;
                a.download = `Shot_on_iOS_${file.name}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };

            // Switch to result view
            uploadPanel.style.display = 'none';
            resultPanel.style.display = 'block';

        } catch (error) {
            console.error('上传失败:', error);
            alert('生成水印时出错: ' + error.message);
            // Revert state
            dropzone.style.display = 'block';
            loader.style.display = 'none';
        }
    }
});
