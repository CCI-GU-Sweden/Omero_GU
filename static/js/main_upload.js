document.addEventListener('DOMContentLoaded', () => {
    const keysEndpoint = '/get_existing_tags';
    const interactiveKeyDropdown = document.getElementById('interactive-key-dropdown');
    const interactiveNewInput = document.getElementById('interactive-new-input');
    const interactiveExistingDropdown = document.getElementById('interactive-existing-dropdown');
    const newRadio = document.getElementById('new-value-radio');
    const existingRadio = document.getElementById('existing-value-radio');
    const addButton = document.getElementById('add-key-value-pair');
    const staticSection = document.getElementById('static-section');
    const fileInput = document.getElementById('file-input');
    const folderInput = document.getElementById('folder-input');
    const selectFolderButton = document.getElementById('select-folder-button');
    const importButton = document.getElementById('import-button');
    const fileList = document.getElementById('file-list');
    const disconnectButton = document.getElementById('disconnect-button');
    const projectDropdown = document.getElementById('project-dropdown');
    const clearButton = document.getElementById('clear-button');

    let fileStore = {}; // Maps file names to File objects

    function getImportedFiles() {
        return JSON.parse(localStorage.getItem('importedFiles') || '[]');
    }

    function saveKeyValuePairs() {
        const keyValuePairs = [];
        document.querySelectorAll('.static-row').forEach(row => {
            const key = row.querySelector('label:first-child').textContent.replace('Key: ', '');
            const value = row.querySelector('label:nth-child(2)').textContent.replace('Value: ', '');
            keyValuePairs.push({ key, value });
        });
        localStorage.setItem('keyValuePairs', JSON.stringify(keyValuePairs));
        console.log('Key-Value Pairs:', keyValuePairs);
    }

    function loadExistingValues(key, values) {
        if (!values || !Array.isArray(values)) values = [];
        interactiveExistingDropdown.innerHTML = values
            .map(value => `<option value="${value.trim()}">${value.trim()}</option>`)
            .join('');
    }

    function renderFileList() {
        const importedFiles = getImportedFiles();
        fileList.innerHTML = '';
        importButton.disabled = importedFiles.length === 0;

        const fileCountLabel = document.getElementById('file-count-label');
        fileCountLabel.textContent = importedFiles.length
            ? `${importedFiles.length} file(s) ready for import`
            : 'No files selected for import';

        importedFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = `file-item ${file.status}`;
            fileItem.textContent = `${file.name}: ${file.message}${file.path ? `. Stored at ${file.path}` : ''}`;

            const removeButton = document.createElement('button');
            removeButton.textContent = 'Remove';
            removeButton.className = 'remove-button';
            removeButton.addEventListener('click', () => {
                importedFiles.splice(index, 1);
                localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
                delete fileStore[file.name];
                renderFileList();
            });

            fileItem.appendChild(removeButton);
            fileList.appendChild(fileItem);
        });
    }

    function handleFiles(files) {
        const importedFiles = getImportedFiles();

        Array.from(files).forEach(file => {
            if (!importedFiles.some(existingFile => existingFile.name === file.name)) {
                const fileObj = {
                    name: file.name,
                    size: file.size,
                    status: 'pending',
                    message: 'Pending upload',
                    path: ''
                };
                fileStore[file.name] = file;
                importedFiles.push(fileObj);
            }
        });

        localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
        renderFileList();
    }

    // Fetch keys and populate dropdown
    fetch(keysEndpoint)
        .then(response => response.json())
        .then(keysAndValues => {
            const keys = Object.keys(keysAndValues);
            interactiveKeyDropdown.innerHTML = keys
                .map(key => `<option value="${key}">${key}</option>`)
                .join('');

            if (keys.length > 0) loadExistingValues(keys[0], keysAndValues[keys[0]]);
        })
        .catch(console.error);

    interactiveKeyDropdown.addEventListener('change', () => {
        const selectedKey = interactiveKeyDropdown.value;
        fetch(keysEndpoint)
            .then(response => response.json())
            .then(keysAndValues => {
                loadExistingValues(selectedKey, keysAndValues[selectedKey] || []);
            })
            .catch(console.error);
    });

    newRadio.addEventListener('change', () => {
        interactiveNewInput.disabled = false;
        interactiveExistingDropdown.disabled = true;
    });

    existingRadio.addEventListener('change', () => {
        interactiveNewInput.disabled = true;
        interactiveExistingDropdown.disabled = false;
    });

    addButton.addEventListener('click', () => {
        const key = interactiveKeyDropdown.value;
        const value = newRadio.checked ? interactiveNewInput.value : interactiveExistingDropdown.value;

        if (!value) {
            alert('Please enter or select a value!');
            return;
        }

        const existingRow = Array.from(staticSection.children).find(row =>
            row.querySelector('label:first-child').textContent.includes(`Key: ${key}`)
        );

        if (existingRow) {
            existingRow.querySelector('label:nth-child(2)').textContent = `Value: ${value}`;
        } else {
            const staticRow = document.createElement('div');
            staticRow.className = 'static-row';
            staticRow.innerHTML = `
                <label>Key: ${key}</label>
                <label>Value: ${value}</label>
                <button class="remove-row">Remove</button>
            `;
			
            staticRow.querySelector('.remove-row').addEventListener('click', () => {
                staticRow.remove();
                saveKeyValuePairs();
            });
			staticRow.querySelector('.remove-row').classList.add('remove-button');
            staticSection.appendChild(staticRow);
        }

        saveKeyValuePairs();
        interactiveNewInput.value = '';
        if (newRadio.checked) interactiveNewInput.focus();
    });

    clearButton.addEventListener('click', () => {
        localStorage.setItem('importedFiles', '[]');
        renderFileList();
        importButton.disabled = true;
    });

    fileInput.addEventListener('change', () => handleFiles(fileInput.files));
    folderInput.addEventListener('change', () => handleFiles(folderInput.files));
    selectFolderButton.addEventListener('click', () => folderInput.click());

    importButton.addEventListener('click', (e) => {
		console.log("starting upload");
        e.preventDefault();
		
		const formData = new FormData();
		const importedFiles = getImportedFiles();

		importedFiles.forEach(fileObj => {
			if (fileObj.status === 'pending') {
				fileObj.status = 'uploading';
				fileObj.message = 'Uploading in progress...';
				const file = fileStore[fileObj.name];
                if (file) formData.append('files', file);
				console.log(`Uploading file: ${file.name} -> ${fileObj.status}`);
			}
		});
		localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
		renderFileList();

        const keyValuePairs = JSON.parse(localStorage.getItem('keyValuePairs') || '[]');
        formData.append('keyValuePairs', JSON.stringify(keyValuePairs));

		importButton.disabled = true; //disable import button
	
        fetch(importImagesUrl, {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(result => {
                if (result.files) {
                    result.files.forEach(file => {
                        const updatedFile = importedFiles.find(f => f.name === file.name);
                        if (updatedFile) {
                            updatedFile.status = file.status;
                            updatedFile.message = file.message;
                            updatedFile.path = file.path;
                        }
                    });

                    localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
                    renderFileList();
					importButton.disabled = true; //disable import button
                }
            })
            .catch(console.error);
    });

    disconnectButton.addEventListener('click', () => {
        fileStore = {};
        localStorage.removeItem('importedFiles');
        renderFileList();

        fetch('/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(response => {
                alert(`You have been disconnected, redirecting to ${response.url}`);
                window.location.href = response.url;
            })
            .catch(console.error);
    });

    document.getElementById('custom-file-input').addEventListener('click', () => fileInput.click());

    window.onerror = (message, source, lineno, colno, error) => {
        fetch('/log-error', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, source, lineno, colno, error: error.stack })
        });
    };

    renderFileList();
    disconnectButton.style.display = 'block';
	
	// Check if any files are currently uploading
	function checkIfUploading() {
		const importedFiles = JSON.parse(localStorage.getItem('importedFiles')) || [];
		return importedFiles.some(file => file.status === 'uploading');
	}

	// Add a listener for the beforeunload event to warn users about ongoing uploads
	window.addEventListener('beforeunload', (event) => {
		if (checkIfUploading()) {
			event.preventDefault();
			event.returnValue = ''; // This triggers the browser's "are you sure?" dialog
		}
	});
	
});
//clean the local storage if the page is reloaded. Important for keyValuePair, it can persist!
localStorage.removeItem('keyValuePairs');
localStorage.removeItem('importedFiles');