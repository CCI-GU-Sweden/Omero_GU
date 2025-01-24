        const fileInput = document.getElementById('file-input');
        const folderInput = document.getElementById('folder-input');
        const selectFolderButton = document.getElementById('select-folder-button');
        const importButton = document.getElementById('import-button');
        const fileList = document.getElementById('file-list');
        const uploadForm = document.getElementById('upload-form');
        const disconnectButton = document.getElementById('disconnect-button');
        const projectDropdown = document.getElementById('project-dropdown');

        document.addEventListener('DOMContentLoaded', function() {
            localStorage.setItem('importedFiles', '[]');
            // Show the disconnect button
            disconnectButton.style.display = 'block';

            console.log("loaded....")
        });

        function getImportedFiles(){
            return  JSON.parse(localStorage.getItem('importedFiles'));
        }

        // Function to render the file list on the page
		function renderFileList() {
			let importedFiles = getImportedFiles();
			fileList.innerHTML = ''; // Clear the file list

			importedFiles.forEach((file, index) => {
				// Create a container for each file item
				const fileItem = document.createElement('div');
				fileItem.className = `file-item ${file.status}`; // Add status class for styling
				fileItem.textContent = `${file.name}: ${file.message}${file.path ? `. Stored at ${file.path}` : ''}`;

				// Create a "Remove" button
				const removeButton = document.createElement('button');
				removeButton.textContent = 'Remove';
				removeButton.className = 'remove-button'; // Add a class for styling if needed

				// Add event listener for the Remove button
				removeButton.addEventListener('click', function () {
					// Remove the file from the imported files list
					importedFiles.splice(index, 1);

					// Update the list in localStorage and re-render the file list
					localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
					renderFileList();
				});

				// Append the Remove button to the file item
				fileItem.appendChild(removeButton);

				// Append the file item to the list
				fileList.appendChild(fileItem);

				console.log(`Rendered: ${file.name} -> ${file.status}, path: ${file.path}`);
			});
		}
		
		let fileStore = {}; // Maps file names to File objects
		function handleFiles(files) {
			let importedFiles = getImportedFiles();
			importButton.disabled = files.length === 0;

			Array.from(files).forEach(file => {
				if (!importedFiles.some(existingFile => existingFile.name === file.name)) {
					let fileObj = {
						name: file.name,
						size: file.size,
						status: 'pending',
						message: 'Pending upload',
						path: ""
					};

					// Add file reference to fileStore
					fileStore[file.name] = file;

					importedFiles.push(fileObj);
				}
			});

			localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
			renderFileList();
		}


        fileInput.addEventListener('change', function() {
            handleFiles(this.files);
        });

        selectFolderButton.addEventListener('click', function() {
            folderInput.click();
        });

        folderInput.addEventListener('change', function() {
            handleFiles(this.files);
        });

        // Handle form submission to upload files
		uploadForm.addEventListener('submit', function (e) {
			e.preventDefault();
            let importedFiles = getImportedFiles();
			const formData = new FormData();
			
			// Retrieve stored key-value pairs from localStorage
			const keyValuePairs = JSON.parse(localStorage.getItem('keyValuePairs')) || [];
			if (keyValuePairs.length > 0) {
				formData.append('keyValuePairs', JSON.stringify(keyValuePairs));
				console.log("Added key-value pairs");
				console.log(keyValuePairs);
			} else {
				consol.log('No key-value pairs added.');
				return;
			}
			
			
		importedFiles.forEach(fileObj => {
			if (fileObj.status === 'pending') {
				// Retrieve the file from fileStore
				const file = fileStore[fileObj.name];
				if (file) {
					formData.append('files', file);
				}
			}
		});


			importButton.disabled = true;

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
								updatedFile.status = file.status; // 'success', 'error', or 'duplicate'
								updatedFile.message = file.message;
                                updatedFile.path = file.path;
								console.log(`Updated file: ${file.name} -> ${file.status}`);
							}
						});

						// Save updated statuses to localStorage
						localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
						console.log("Updated importedFiles:", importedFiles);
						
						// Re-render the file list to reflect the new statuses
						renderFileList();
					} else {
						console.error('Unexpected server response:', result);
					}

					importButton.disabled = false;
				})
				.catch(error => {
					console.error('Error:', error);
					alert('An error occurred during import');
					importButton.disabled = false;
				});
		});

		removeButton.addEventListener('click', function () {
			// Remove the file from fileStore
			delete fileStore[importedFiles[index].name];
			
			// Remove the file metadata from localStorage
			importedFiles.splice(index, 1);
			localStorage.setItem('importedFiles', JSON.stringify(importedFiles));
			renderFileList();
		});


        // Handle disconnect (clear session and localStorage)
        disconnectButton.addEventListener('click', function () {
			fileStore = {}; // Clear fileStore
            localStorage.removeItem('importedFiles');
            importedFiles = [];
            renderFileList();
            fetch('{{ url_for("logout") }}', {
                method: 'POST',
                //body: JSON.stringify(data),
                headers: {
                  'Content-Type': 'application/json'
                }
              })
              .then(response => { 
                alert('You have been disconnected, redirecting to ' + response.url);
                window.location.href = response.url;
            })
            .catch(error => console.error('Error:', error));
		});

        window.onerror = function(message, source, lineno, colno, error) {
            fetch('/log-error', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    source: source,
                    lineno: lineno,
                    colno: colno,
                    error: error.stack
                })
            });
        };