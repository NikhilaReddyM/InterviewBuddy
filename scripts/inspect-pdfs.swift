// Phase 1 only. Run from repository root on macOS; no network or model calls.
import Foundation
import PDFKit
import Vision
import AppKit

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let source = root.appendingPathComponent("src/docs")
let output = root.appendingPathComponent("backend/data/phase1")
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let files = try FileManager.default.contentsOfDirectory(at: source, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "pdf" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
var inventory: [[String: Any]] = []
var samples: [[String: Any]] = []
// Content pages, deliberately excluding introductory title pages.
let selections: [String: [Int]] = [
    "Dynamic Programming.pdf": [10, 40, 80],
    "Sliding Windows 1.pdf": [5, 15, 25],
    "Binary search variants - 1.pdf": [8, 25, 45]
]
for (fileIndex, file) in files.enumerated() {
    guard let document = PDFDocument(url: file), !document.isLocked else {
        inventory.append(["filename": file.lastPathComponent, "error": "Unreadable or locked PDF"])
        continue
    }
    var counts: [Int] = []
    for index in 0..<document.pageCount {
        counts.append((document.page(at: index)?.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines).count)
    }
    inventory.append(["filename": file.lastPathComponent, "pages": document.pageCount,
                      "lowTextPages": counts.filter { $0 < 80 }.count,
                      "charactersPerPage": counts])
    print("Inspected \(file.lastPathComponent): \(document.pageCount) pages")
    for number in selections[file.lastPathComponent] ?? [] {
        guard let page = document.page(at: number - 1) else { continue }
        let prefix = "document-\(fileIndex + 1)-page-\(number)"
        let direct = page.string ?? ""
        try direct.write(to: output.appendingPathComponent(prefix + "-direct.txt"), atomically: true, encoding: .utf8)
        let image = page.thumbnail(of: NSSize(width: 2400, height: 2400), for: .mediaBox)
        var rect = NSRect(origin: .zero, size: image.size)
        guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { continue }
        let bitmap = NSBitmapImageRep(cgImage: cgImage)
        try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(prefix + ".png"))
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        request.usesLanguageCorrection = false // Avoid dictionary corrections to identifiers.
        var result: [String: Any] = ["filename": file.lastPathComponent, "page": number,
                                    "prefix": prefix, "directCharacters": direct.count]
        do {
            try VNImageRequestHandler(cgImage: cgImage).perform([request])
            let observations = request.results ?? []
            let lines: [[String: Any]] = observations.compactMap { observation in
                guard let text = observation.topCandidates(1).first else { return nil }
                let box = observation.boundingBox
                return ["text": text.string, "confidence": text.confidence,
                        "box": ["x": box.minX, "y": box.minY, "width": box.width, "height": box.height]]
            }
            let text = lines.compactMap { $0["text"] as? String }.joined(separator: "\n")
            try text.write(to: output.appendingPathComponent(prefix + "-ocr.txt"), atomically: true, encoding: .utf8)
            try JSONSerialization.data(withJSONObject: lines, options: [.prettyPrinted, .sortedKeys])
                .write(to: output.appendingPathComponent(prefix + "-ocr.json"))
            result["ocrCharacters"] = text.count
            result["recognizedRegions"] = lines.count
            result["status"] = "needs visual review"
            print("  Page \(number): direct=\(direct.count), OCR=\(text.count)")
        } catch {
            result["error"] = error.localizedDescription
            print("  Page \(number): OCR failed: \(error)")
        }
        samples.append(result)
    }
}
let report: [String: Any] = ["inventory": inventory, "samples": samples,
    "notes": "Character counts and OCR confidence are not accuracy scores. Page numbers are 1-based PDF positions. Bounding boxes use normalized bottom-left coordinates. Review code and diagrams against PNGs. DOCX is outside this experiment."]
try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
    .write(to: output.appendingPathComponent("report.json"))
print("Private results: backend/data/phase1/report.json")
