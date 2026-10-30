// Local text-only resume extraction using the same PDFKit dependency as the library.
import Foundation
import PDFKit

guard CommandLine.arguments.count == 2,
      let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])),
      !document.isLocked, document.pageCount > 0 else {
    fputs("Unreadable, encrypted, or empty PDF.\n", stderr)
    exit(1)
}
guard document.pageCount <= 30 else {
    fputs("Resume PDFs must contain at most 30 pages.\n", stderr)
    exit(1)
}
var pages: [String] = []
for index in 0..<document.pageCount {
    let text = document.page(at: index)?.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    pages.append(text)
}
// Refuse partial extraction so an image-only page cannot silently lose experience.
guard pages.allSatisfy({ !$0.isEmpty }) else {
    fputs("A PDF page has no readable text. Scanned pages need OCR; upload a text-based PDF or DOCX.\n", stderr)
    exit(1)
}
print(pages.joined(separator: "\n\n"))
