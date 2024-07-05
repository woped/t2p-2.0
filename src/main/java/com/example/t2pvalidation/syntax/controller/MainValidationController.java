package com.example.t2pvalidation.syntax.controller;

import com.example.t2pvalidation.syntax.service.MainValidationService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.Map;

@RestController
@RequestMapping("/main/syntax")
public class MainValidationController {

    @Autowired
    private MainValidationService mainValidationService;

    @PostMapping("/validate")
    public Map<String, Object> validateAll(@RequestParam("file") MultipartFile file) throws IOException {
        File tempFile = File.createTempFile("uploaded-", ".bpmn");
        try (FileOutputStream fos = new FileOutputStream(tempFile)) {
            fos.write(file.getBytes());
        }

        Map<String, Object> result = mainValidationService.validateAll(tempFile.getAbsolutePath());
        // Delete the temporary file
        tempFile.delete();

        return result;
    }
}
