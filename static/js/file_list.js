//import { pairFiles } from "./utils.js";
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

function splitName(name) {
  // pair by *basename* only; ignore path - can lead to issue with folder upload
  const base = name.split(/[\\/]/).pop();
  const i = base.lastIndexOf('.');
  if (i < 0) return { stem: base.toLowerCase(), ext: "" };
  return { stem: base.slice(0, i).toLowerCase(), ext: base.slice(i + 1).toLowerCase() };
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


function splitRelPath(file) {
  // Prefer folder-aware relative path, fall back to name
  const rel = (file.webkitRelativePath && file.webkitRelativePath.length)
    ? file.webkitRelativePath
    : file.name;

  // Normalize separators and case (Windows-safe)
  const norm = rel.replace(/\\/g, '/');
  const parts = norm.split('/');
  const base = parts.pop();                    // "Img.tif"
  const dir  = parts.join('/').toLowerCase();  // "run_42/pos_001" (or "")

  const dot = base.lastIndexOf('.');
  const stem = (dot < 0 ? base : base.slice(0, dot)).toLowerCase(); // "img"
  const ext  = (dot < 0 ? ""   : base.slice(dot + 1)).toLowerCase(); // "tif"

  return { dir, stem, ext };
}

function buildPairs(files) {
  // group by directory, then by stem
  const groups = new Map(); // dir -> stem -> ext -> [File]
  for (const f of files) {
    const { dir, stem, ext } = splitRelPath(f);
    if (!groups.has(dir)) groups.set(dir, new Map());
    const stems = groups.get(dir);
    if (!stems.has(stem)) stems.set(stem, {});
    (stems.get(stem)[ext] ||= []).push(f);
  }

  const pairs = [];     // { ext1: File, ext2: File, kind: 'emiSer'|'primaryXml' }
  const singles = [];   // unmatched non-XML
  const droppedXml = []; // XML singletons are removed from UI

  for (const [, stems] of groups) {
    for (const [, exts] of stems) {
      const emis = exts["emi"] || [];
      const sers = exts["ser"] || [];
      const xmls = exts["xml"] || [];

      // 1) Prefer explicit EMI+SER pairing
      if (emis.length && sers.length) {
        pairs.push({ ext1: emis[0], ext2: sers[0], kind: "emiSer" });
        singles.push(...emis.slice(1), ...sers.slice(1));  // extras unmatched
        droppedXml.push(...xmls);                          // ignore sidecar XML in UI
        continue;
      }

      // 2) Generic PRIMARY + XML (any non-xml in the SAME directory)
      const nonXmlExts = Object.keys(exts).filter(e => e !== "xml");
      const nonXmlFiles = nonXmlExts.flatMap(e => exts[e]);

      if (xmls.length && nonXmlFiles.length) {
        const n = Math.min(xmls.length, nonXmlFiles.length);
        for (let i = 0; i < n; i++) {
          pairs.push({ ext1: nonXmlFiles[i], ext2: xmls[i], kind: "primaryXml" });
        }
        singles.push(...nonXmlFiles.slice(n)); // leftover primaries
        droppedXml.push(...xmls.slice(n));     // leftover XMLs dropped
        continue;
      }

      // 3) No pair: keep non-XML as singles, drop XML-only
      for (const ext of Object.keys(exts)) {
        if (ext === "xml") droppedXml.push(...exts[ext]);
        else singles.push(...exts[ext]);
      }
    }
  }

  return { pairs, singles, droppedXml };
}


export function addFilesToList(listOfFileObjs) {
  const { pairs, singles, _ } = buildPairs(Array.from(listOfFileObjs));

  // Add unmatched primaries
  singles.forEach(f => addFileToList(f));

  // Add pairs
  pairs.forEach(p => checkAndAddFilePairToList(p));
}


// export function addFilesToList(listOfFileObjs){
//     var emi = "emi";
//     var ser = "ser";
//     var mrc = "mrc";
//     var xml = "xml"
//     var emiSerPairs = pairFiles(listOfFileObjs, "emi","ser");
//     var mrcXmlPairs = pairFiles(listOfFileObjs, "mrc","xml");
//     var singleFiles = Array.from(listOfFileObjs).filter((file) => !checkExtMatch(file,[emi,ser,mrc,xml]));

//     Array.from(singleFiles).forEach((file, index) => {
//         addFileToList(file);
//     });

//     Array.from([...emiSerPairs,...mrcXmlPairs]).forEach((file, index) => {
//         checkAndAddFilePairToList(file);
//     });
// }

export function clearFileList()
{
    for(var c of fileComponents)
        c.delete();

    fileComponents = [];
    callCCB();
}

export function updateFileStatus(fileName, fileStatus, message)
{
    var fName = fileName.split(/[/\\]/).pop();
    var fileData = Array.from(fileComponents).find((element) => element.getName() == fName);
    if(fileData)
        fileData.setStatus(fileStatus,message);
}

export function updateRetryStatus(fileName, retry, maxRetries)
{
    var fileData = Array.from(fileComponents).find((element) => element.getName() == fileName);
    if(fileData)
        fileData.setRetryText(retry,maxRetries);
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
