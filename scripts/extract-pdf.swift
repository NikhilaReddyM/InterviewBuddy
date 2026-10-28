// Local Phase 2 worker: input PDF, output directory. JSON and page images only.
import Foundation
import PDFKit
import Vision
import AppKit

guard CommandLine.arguments.count == 3 else { fatalError("Usage: extract-pdf input.pdf output-directory") }
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
guard let document = PDFDocument(url: input), !document.isLocked, document.pageCount > 0 else {
    fputs("Unreadable, encrypted, or empty PDF\n", stderr); exit(1)
}
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
for index in 0..<document.pageCount {
    try autoreleasepool {
        guard let page = document.page(at: index) else { throw NSError(domain: "PDF", code: 1) }
        let number = index + 1
        let direct = page.string ?? ""
        var record: [String: Any] = ["number": number, "direct_text": direct, "ocr_text": "", "regions": []]
        var issues = ["Review code, formulas, and diagram relationships against original."]
        if direct.trimmingCharacters(in: .whitespacesAndNewlines).count < 80 { issues.append("Little direct text; may be an image or blank page.") }
        let image = page.thumbnail(of: NSSize(width: 2400, height: 2400), for: .mediaBox)
        var rect = NSRect(origin: .zero, size: image.size)
        guard let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { throw NSError(domain: "Render", code: 1) }
        let bitmap = NSBitmapImageRep(cgImage: cg)
        try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent("\(number).png"), options: .atomic)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        request.usesLanguageCorrection = false
        do {
            try VNImageRequestHandler(cgImage: cg).perform([request])
            let regions: [[String: Any]] = (request.results ?? []).compactMap { observation in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                let b = observation.boundingBox
                return ["text": candidate.string, "confidence": candidate.confidence,
                        "box": ["x": b.minX, "y": b.minY, "width": b.width, "height": b.height]]
            }
            record["regions"] = regions
            record["ocr_text"] = regions.compactMap { $0["text"] as? String }.joined(separator: "\n")
            if regions.isEmpty { issues.append("OCR found no text; inspect before confirming blank.") }
        } catch { issues.append("OCR failed: \(error.localizedDescription)") }
        record["issues"] = issues
        try JSONSerialization.data(withJSONObject: record).write(to: output.appendingPathComponent("\(number).json"), options: .atomic)
        print("Extracted PDF page \(number)/\(document.pageCount)")
        fflush(stdout)
    }
}
