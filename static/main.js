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

    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });

    async function handleFile(file) {
        if (!file.type.startsWith('image/')) {
            alert('请上传图片文件');
            return;
        }

        // Show loader
        uploadPanel.style.display = 'none';
        loader.style.display = 'block';

        try {
            const location = document.getElementById('location-input').value;
            const formData = new FormData();
            formData.append('file', file);
            formData.append('location', location);
            formData.append('return_bar', 'false'); // 获取全图以保留 EXIF

            const response = await fetch('/v1/watermark/png', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('生成失败');

            const blob = await response.blob();
            if (currentFileUrl) URL.revokeObjectURL(currentFileUrl);
            currentFileUrl = URL.createObjectURL(blob);
            resultImage.src = currentFileUrl;

            loader.style.display = 'none';
            resultPanel.style.display = 'block';
        } catch (err) {
            alert('处理出错: ' + err.message);
            loader.style.display = 'none';
            uploadPanel.style.display = 'block';
        }
    }

    btnBack.addEventListener('click', () => {
        resultPanel.style.display = 'none';
        uploadPanel.style.display = 'block';
        fileInput.value = '';
    });

    btnDownload.addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = resultImage.src;
        a.download = `watermark_${Date.now()}.jpg`;
        a.click();
    });
});
