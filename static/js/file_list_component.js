export const FileStatus = Object.freeze({

    PENDING: "pending", //added to lists to upload
    QUEUED: "queued", //waiting for transfer to the "flask server"
    STAGING: "staging", //transfering file to "flask server"
    STARTED: "started", //starting upload to omero from "flask server"
//    UPLOADING: "uploading",
    PROGRESS: "progress", //progress of upload to omero
    IMPORTING: "importing", //omero server is importing and finalizing

    SUCCESS: "success", //transer and import to omero complete and successfull
    CONVERTING: "converting",

    UNSUPPORTED_FORMAT: "unsupported_format",
    DUPLICATE: "duplicate",
    UNMATCHED: "unmatched",

    ERROR: "error",
});

export class FileListComponent {

    constructor(parentElement, fileObj, isChild, status)
    {

        this.fileObj = fileObj;
        this.container = document.createElement("div");
        this.container.textContent = fileObj.name + " (" + (fileObj.size/1048576).toFixed(2) + " MB)";
        this.container.dataset.name = fileObj.name;

        this.status = status;
        this.container.classList.add('file-item');
        this.container.classList.add(this.status);
        if(isChild)
            this.container.classList.add('child');

        var className = `file-item ${status}`;
        
        this.statusText = document.createElement('p');
        this.statusText.textContent += this.status;
        this.statusText.classList.add("status");
        this.container.appendChild(this.statusText);

        this.retryText = document.createElement('p');
        this.retryText.textContent = "";
        this.retryText.classList.add("retry");
        this.container.appendChild(this.retryText);


        if(!isChild){
            this.removeButton = document.createElement('button');
            this.removeButton.textContent = 'Remove';
            this.removeButton.className = 'remove-button';
            this.removeButton.addEventListener('click', () => this.destroy());
            this.container.appendChild(this.removeButton);
        }
        else{
            const childText = document.createElement('p');
            childText.textContent += "-";
            this.container.appendChild(childText);    
        }

        parentElement.appendChild(this.container);
    }

    disableRemove(){
        if(this.removeButton)
            this.removeButton.disabled = true;
    }

    setStatus(status){
        this.setStatus(status,"");
    }

    setStatus(status, message)
    {
        console.log("setting component status: " + status);
        this.container.classList.remove(this.status);
        this.status = status;
        this.container.classList.add(status);
        this.statusText.textContent = this.createStatusString(status,message);
        if(this.child)
            this.child.setStatus(status,message);

        if(status == FileStatus.SUCCESS)
            this.clearRetryText()
    }

    createStatusString(status, message){
        switch(status){
            case FileStatus.PROGRESS:
                return message;
            case FileStatus.SUCCESS:
                return message;
            case FileStatus.STARTED:
                return message;
            case FileStatus.ERROR:
                return FileStatus.ERROR + " " + message;
            case FileStatus.QUEUED:
                return "Queued for transfer " + message;
            case FileStatus.STAGING:
                return "Staging file... " + message;
            case FileStatus.IMPORTING:
                return "Importing and finalizing..."
            case FileStatus.UNSUPPORTED_FORMAT:
                return "Unsupported format: " + message
            default:
                return status;
        }
    }

    clearRetryText(){
        this.retryText.textContent = "";
    }

    setRetryText(retry, maxRetries){
        if(retry == "1")
            return;

        var msg = "retry: " + retry + "/" + maxRetries;
        this.retryText.textContent = msg;
    }

    getName(){
        return this.fileObj.name;
    }
    
    getStatus(){
        return this.status;
    }

    getFileSize(){
        return this.fileObj.size;
    }

    setChildComponent(child){
        this.child = child;
    }

    getChildComponent(){
        if(this.child)
            return this.child;

        return null;
    }

    hasChildComponent(){
        if(this.child)
            return true;

        return false;
    }

    setDestroyCallback(cb){
        this.onDestroy=cb;
    }

    delete(recurse = true){

        this.container.remove();
        this.container = null;
        this.statusText = null;
        this.status = null;
        this.removeButton = null;
        if(recurse && this.child){
            this.child.delete();
            this.child = null;
        }
        console.log("FileListComponent removed from DOM.");
    }

    destroy(){

        if(this.child){
            this.child.destroy()
        }

        if(this.onDestroy)
            this.onDestroy(this);

        this.child == null
        this.delete(false);
        


        
    }
}