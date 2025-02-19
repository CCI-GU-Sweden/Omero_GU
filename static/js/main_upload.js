import { fetchWrapper, showErrorPage } from "./utils.js";
import { updateFileStatus, addFilesToList, getFileListForImport, nrFilesForUpload, clearFileList, setFileListChangeCB } from "./file_list.js";
import { FileStatus } from "./file_list_component.js";

document.addEventListener('DOMContentLoaded', () => {
    const keysEndpoint = '/get_existing_tags';
    const formatsEndPoint = '/supported_file_formats';
    const importImagesUrl = '/import_images';
    const importUpdateStream = '/import_updates'
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
    const disconnectButton = document.getElementById('disconnect-button');
    const clearButton = document.getElementById('clear-button');
	const groupsEndpoint = '/get_existing_groups';
	const groupDropdown = document.getElementById('group-dropdown');
	const defaultGroupEndpoint = "/get_default_group";

    function readAndSetSupportedFileFormats()
    {
        fetchWrapper(formatsEndPoint)
            .then(formats => {
                var folderFormatList = formats.folder_formats;
                var singleFormatList = formats.single_formats;
                document.getElementById("file-input").accept = singleFormatList.join(',');
                document.getElementById("folder-input").accept = folderFormatList.join(',');
            })
            .catch(error => {
                console.log("VAADD?!?! " + error.message);
                //alert(error.type + " occured!\nNotify the CCI staff promptly and show them this message: " + error.message);
                showErrorPage(error.type,error.message);
           })   
    }

    function updateImportStatus()
    {
        var importCnt = nrFilesForUpload();
        importButton.disabled = importCnt == 0;
        const fileCountLabel = document.getElementById('file-count-label');
        fileCountLabel.textContent = importCnt 
            ? `${importCnt} object(s) ready for conversion/import`
            : 'No files selected for conversion/import';
    }

    function getTags(){
        fetchWrapper(keysEndpoint)
            .then(keysAndValues => {
                const keys = Object.keys(keysAndValues);
                interactiveKeyDropdown.innerHTML = keys
                    .map(key => `<option value="${key}">${key}</option>`)
                    .join('');
        
                if (keys.length > 0) loadExistingValues(keys[0], keysAndValues[keys[0]]);
            })
            .catch(error => {
                console.log("skit händer här " + error.message);
                //alert(error.type + " occured!\nNotify the CCI staff promptly and show them this message: " + error.message);
                showErrorPage(error.type,error.message);
            })
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

    function handleFiles(files) {

        addFilesToList(files);
        //updateImportStatus();
    }

	function populateGroupDropdown() {
		return fetchWrapper(groupsEndpoint)
			.then(groups => {
				groupDropdown.innerHTML = groups
					.map(group => `<option value="${group}">${group}</option>`)
					.join('');
				return groups; // Return groups for chaining
			})
			.catch(error => {
				console.log("Error fetching groups: " + error.message);
				showErrorPage(error.type, error.message);
			});
	}

	function setDefaultGroup() {
		fetchWrapper(defaultGroupEndpoint)
			.then(defaultGroup => {
				// Ensure the dropdown is populated first
				if ([...groupDropdown.options].some(option => option.value === defaultGroup)) {
					groupDropdown.value = defaultGroup;
				} else {
					console.warn("Default group not found in the list!");
				}
			})
			.catch(error => {
				console.log("Error fetching default group: " + error.message);
				showErrorPage(error.type, error.message);
			});
	}

	// Fetch groups and set the current group
	populateGroupDropdown().then(setDefaultGroup);
    // Fetch keys and populate dropdown
    getTags();
    readAndSetSupportedFileFormats();
    setFileListChangeCB(updateImportStatus);

    interactiveKeyDropdown.addEventListener('change', () => {
        const selectedKey = interactiveKeyDropdown.value;
        getTags();
    });

    newRadio.addEventListener('change', () => {
        interactiveNewInput.disabled = false;
        interactiveExistingDropdown.disabled = true;
    });

    existingRadio.addEventListener('change', () => {
        interactiveNewInput.disabled = true;
        interactiveExistingDropdown.disabled = false;
    });
	
	groupDropdown.addEventListener("change", function() {
		fetch('/set_group', {
			method: 'POST',
			headers: {
				'Accept': 'application/json',
				'Content-Type': 'application/json'
				},
			body: JSON.stringify({ group: groupDropdown.value })
		})
		.then(response => response.json())
		.then(data => console.log("Group set successfully:", data))
		.catch(error => console.error("Error setting group:", error));
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
        clearFileList();
        //updateImportStatus();
    });

    function filterUnsupprtedFiles(listOfFiles, acceptedExtensions){
        const selectedFiles = Array.from(listOfFiles).filter(file => {
            return acceptedExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
        });
        return selectedFiles;
    } 

    fileInput.addEventListener('change', () => handleFiles(filterUnsupprtedFiles(fileInput.files,fileInput.accept.split(','))));
    folderInput.addEventListener('change', () => handleFiles(filterUnsupprtedFiles(folderInput.files,folderInput.accept.split(','))));
    selectFolderButton.addEventListener('click', () => folderInput.click());

    setupEventSource();

    importButton.addEventListener('click', (e) => {
		console.log("Starting upload");
        e.preventDefault();
		
        const importedFiles = getFileListForImport();
		importButton.disabled = true; //disable import button
	
        uploadFiles(importedFiles);
    });

    function uploadFiles(allFiles) {
        const keyValuePairs = JSON.parse(localStorage.getItem('keyValuePairs') || '[]');
        try{
            for (const files of allFiles) {
                const formData = new FormData();
                formData.append('keyValuePairs', JSON.stringify(keyValuePairs));
                for(const file of files){
                    formData.append('files', file);
                    updateFileStatus(file.name,FileStatus.QUEUED, "");
                }
                console.log("sending files");
                //fetch("/import_images", {
                fetch(importImagesUrl, {
                    method: "POST",
                    body: formData,
                })
                .then(response => {
                    console.log(`returned ${response.status}`);
                    return response.json()
                })
                .then(result => {
                    console.log("Client upload done:", result);
                })
                .catch (error => {
                    console.error(`Error uploading:`);
                    for(const file of files){
                        console.error(`${file}`);
                    }
                    console.error(`Error:`, error);

                })
            }
        }catch(error){
            console.log(error);
        }
    }
    

    function setupEventSource() {
        let retryTime = 1000; // Default retry time (3 seconds)
        let eventSource;
    
        function connect() {
            eventSource = new EventSource(importUpdateStream);
            console.log("Setting up event source");
    
            eventSource.onmessage = function(event) {
                if (event.data === 'done') {
                    console.log("Import done");
                    eventSource.close();
                    return;
                } 
    
                var jsondata = event.data;
                //console.log(event);
                var fileInfo = JSON.parse(jsondata);
                updateFileStatus(fileInfo.name, fileInfo.status, fileInfo.message);
            };
    
            eventSource.onerror = function(error) {
                console.error('EventSource failed:', error);
                eventSource.close();
                
                // Attempt to reconnect after the retry time
                setTimeout(connect, retryTime);
            };
    
            // Listen for custom retry time from server
            eventSource.onopen = function(event) {
                const serverRetry = eventSource.url.match(/retry: (\d+)/);
                if (serverRetry) {
                    retryTime = parseInt(serverRetry[1]);
                    console.log(`Server specified retry time: ${retryTime}ms`);
                }
            };
        }
    
        connect(); // Initial connection
    }

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
    disconnectButton.style.display = 'block';
	
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
//localStorage.removeItem('importedFiles');