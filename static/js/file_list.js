import { pairFiles } from "./utils.js";
import { FileListComponent } from "./file_list_component.js"

const FileStatus = Object.freeze({
    PENDING: "pending",
    UNMATCHED: "unmatched",
    SUCCESS: "success",
    ERROR: "error",
    UNSUPPORTED_FORMAT: "unsupported format",
    DUPLICATE: "duplicate",
    UPLOADING: "uploading"
});

let fileComponents = [];
var listChangeCb = null;

function getFileList(){
    return document.getElementById('file-list');
}

// function removePairFromList(index1,index2){
//     const child1ToRemove = fileComponents[index1];
//     const child2ToRemove = fileComponents[index2];
//     fileList.removeChild(child1ToRemove);
//     fileList.removeChild(child2ToRemove);
//     delete fileObjStore[child1ToRemove.textContent];
//     delete fileObjStore[child2ToRemove.textContent];
// }

export function setFileListChangeCB(ccb)
{
    if(ccb)
        listChangeCb = ccb;
}

function callCCB()
{
    if(listChangeCb)
        listChangeCb();
}

function removeFileFromList(index){
    const childToRemove = fileComponents[index]; // index is the position of the child to remove
    var cr = fileComponents.splice(childToRemove,1);
    //delete fileObjStore[cr[0].getName()];
    //cr.destroy();
    cr.destroy();
    cr = null;
    callCCB();
}

function removeFileFromListByName(filename)
{
    const indexToRemove = fileComponents.indexOf(filename);
    removeFileFromList(indexToRemove);
}

export function nrFilesForUpload()
{
    var cnt = 0;
    for(var fc of fileComponents){
        if(fc.getStatus() == FileStatus.PENDING)
            cnt++;
    }

    return cnt;

//    var fileList = getFileList();
//    return fileList.childElementCount;
}

function checkAndAddFilePairToList(filePair)
{
    if(filePair.ext1 == null)
        addFileToList(filePair.ext2, FileStatus.UNMATCHED);
    else if(filePair.ext2 == null)
        addFileToList(filePair.ext1, FileStatus.UNMATCHED);
    else
    {
        addPairToList(filePair);
    }
}

function addPairToList(filePair)
{
    var inList1 = fileAlreadyInList(filePair.ext1);
    var inList2 = fileAlreadyInList(filePair.ext2);
    if(inList1 && inList2)
        return
    if(inList1)
        removeFileFromListByName(filePair.ext1.name);
    if(inList2)
        removeFileFromListByName(filePair.ext2.name);

    // var fileList = getFileList();
    // var nc1 = fileList.childElementCount;
    // var nc2 = nc1 +1;

    var parent = createComponent(filePair.ext1,FileStatus.PENDING)
    var child = createComponent(filePair.ext2,FileStatus.PENDING,true)
    parent.setChildComponent(child);
    addToFileList(parent);

}

function addFileToList(fileObj, status=FileStatus.PENDING)
{
    if(fileAlreadyInList(fileObj.name))
        return;
    var comp = createComponent(fileObj,status);
    addToFileList(comp);
}

function checkExtMatch(fileObj, listOfExts)
{
    var ext = fileObj.name.split('.').pop();
    return listOfExts.includes(ext)
}

export function addFilesToList(listOfFileObjs){
    var emi = "emi";
    var ser = "ser";
    var mrc = "mrc";
    var xml = "xml"
    var emiSerPairs = pairFiles(listOfFileObjs, "emi","ser");
    var mrcXmlPairs = pairFiles(listOfFileObjs, "mrc","xml");
    var singleFiles = Array.from(listOfFileObjs).filter((file) => !checkExtMatch(file,[emi,ser,mrc,xml]));

    Array.from(singleFiles).forEach((file, index) => {
        addFileToList(file);
    });

    Array.from([...emiSerPairs,...mrcXmlPairs]).forEach((file, index) => {
        checkAndAddFilePairToList(file);
    });
}

export function clearFileList()
{
    for(var c of fileComponents)
        c.delete();

    fileComponents = [];
    callCCB();
}

function findParentComponentByAnyName(fileName) {
  return fileComponents.find(comp => {
    if (!comp) return false;
    if (comp.getName?.() === fileName) return true;

    if (comp.hasChildComponent?.()) {
      const child = comp.getChildComponent?.();
      return child?.getName?.() === fileName;
    }
    return false;
  });
}

export function updateFileStatus(fileName, fileStatus, message) {
  const fName = fileName.split(/[/\\]/).pop();

  const parent = findParentComponentByAnyName(fName);
  if (!parent) return;

  // Always update parent; parent propagates to child
  parent.setStatus(fileStatus, message);

  // Reorder by recent update (parent is the unit)
  const index = fileComponents.indexOf(parent);
  if (index !== -1) {
    fileComponents.splice(index, 1);

    if (fileStatus === FileStatus.DUPLICATE) fileComponents.push(parent);
    else fileComponents.unshift(parent);

    renderListOrder();
    callCCB();
  }
}



export function updateRetryStatus(fileName, retry, maxRetries) {
  // Find either parent or child; apply text on the matching component
  for (const comp of fileComponents) {
    if (!comp) continue;

    if (comp.getName?.() === fileName) {
      comp.setRetryText(retry, maxRetries);
      return;
    }

    if (comp.hasChildComponent?.()) {
      const child = comp.getChildComponent?.();
      if (child?.getName?.() === fileName) {
        child.setRetryText(retry, maxRetries);
        return;
      }
    }
  }
}



export function setAllPendingToError(message)
{
    fileComponents.forEach(fc => {
        console.log("fc status: " , fc.getStatus());
        if(fc.getStatus() == FileStatus.PENDING)
            fc.setStatus(FileStatus.ERROR,message)
    });
}


function fileAlreadyInList(fileName){

    var fileData = Array.from(fileComponents).find((element) => element.getName() == fileName);
    return Boolean(fileData);
}

function onDestroyCallback(component){
    var idx = fileComponents.indexOf(component);
    if(idx >= 0)
        fileComponents.splice(idx,1);

    callCCB();
}

function createComponent(fileObj, status, isChild=false){
    var comp = new FileListComponent(getFileList(),fileObj,isChild,status);
    comp.setDestroyCallback(onDestroyCallback);
    return comp;
}

function addToFileList(fileComponent){
    const insertIndex = fileComponents.findIndex(file => fileComponent.getFileSize() < file.getFileSize());
    // If no such file, insertIndex will be -1 => append to end
    console.log("inserting at index: " + insertIndex);
    if (insertIndex === -1) {
        fileComponents.push(fileComponent);
    } else {
        fileComponents.splice(insertIndex, 0, fileComponent);
    }

    callCCB();
}

export function getFileListForImport()
{
    var returnList = []
    Array.from(fileComponents).forEach((comp) => {
        if( comp.getStatus() == FileStatus.PENDING)
        {
            comp.disableRemove();
            if(comp.hasChildComponent()){
                var child = comp.getChildComponent();
                returnList.push([comp.fileObj,child.fileObj]);
            }
            else
                returnList.push([comp.fileObj]);
        }
    });

    return returnList;
}

function renderListOrder() {
  const list = getFileList();

  // 1) Record current positions (parent + child)
  const nodes = [];
  for (const comp of fileComponents) {
    if (comp?.container instanceof Node) nodes.push(comp.container);

    if (comp?.hasChildComponent?.()) {
      const child = comp.getChildComponent?.();
      if (child?.container instanceof Node) nodes.push(child.container);
    }
  }

  const first = new Map();
  for (const el of nodes) {
    first.set(el, el.getBoundingClientRect());
  }

  // 2) Reorder DOM (parent + child)
  for (const comp of fileComponents) {
    if (comp?.container instanceof Node) list.appendChild(comp.container);

    if (comp?.hasChildComponent?.()) {
      const child = comp.getChildComponent?.();
      if (child?.container instanceof Node) list.appendChild(child.container);
    }
  }

  // 3) Measure new positions and animate the delta
  for (const el of nodes) {
    const f = first.get(el);
    if (!f) continue;

    const last = el.getBoundingClientRect();
    const dx = f.left - last.left;
    const dy = f.top - last.top;

    // If it didn't move, skip
    if (dx === 0 && dy === 0) continue;

    // Invert
    el.style.transform = `translate(${dx}px, ${dy}px)`;
    el.style.transition = "transform 0s";

    el.classList.add("moving");

    // Play
    requestAnimationFrame(() => {
      el.style.transition = "transform 400ms ease";
      el.style.transform = "";
    });

    // Cleanup transition property after
    el.addEventListener(
      "transitionend",
      () => {
        el.style.transition = "";
        el.style.transform = "";
        el.classList.remove("moving");
      },
      { once: true }
    );
  }
}

