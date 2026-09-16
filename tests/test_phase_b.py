#!/usr/bin/env python3
"""Unit tests for Phase B improvements: Go & Rust AST parsers and canonical noise sanitizer."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

from antigravity_cheaper import agy_ast, cli, noise_sanitizer


class TestPhaseB(unittest.TestCase):
    """Test suite for Phase B multi-language AST parsers and noise sanitizer."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_go_skeleton_elision(self):
        code = """package main

import "fmt"

type Storage interface {
    Get(key string) ([]byte, error)
}

type Node struct {
    ID int
}

func (n *Node) Sync(peer string) error {
    fmt.Println("Syncing peer", peer)
    return nil
}

func ComputeHash(data []byte) string {
    return "sha256"
}
"""
        skel = agy_ast.go_skeleton(code)
        self.assertIn("package main", skel)
        self.assertIn("type Storage interface", skel)
        self.assertIn("type Node struct", skel)
        self.assertIn("func (n *Node) Sync(peer string) error {", skel)
        self.assertIn("func ComputeHash(data []byte) string {", skel)
        # Bodies must be elided
        self.assertNotIn("Syncing peer", skel)
        self.assertNotIn('return "sha256"', skel)
        self.assertIn("...", skel)

    def test_go_symbols_extraction(self):
        code = """package main

type Cache struct {
    capacity int
}

type Store interface {
    Save()
}

func (c *Cache) Evict() bool {
    return true
}

func NewCache(cap int) *Cache {
    return &Cache{capacity: cap}
}
"""
        symbols = agy_ast.go_symbols(code)
        names = [s["name"] for s in symbols]
        kinds = [s["kind"] for s in symbols]

        self.assertIn("Cache", names)
        self.assertIn("Store", names)
        self.assertIn("Evict", names)
        self.assertIn("NewCache", names)

        self.assertIn("struct", kinds)
        self.assertIn("interface", kinds)
        self.assertIn("method", kinds)
        self.assertIn("function", kinds)

        evict_sym = next(s for s in symbols if s["name"] == "Evict")
        self.assertEqual(evict_sym["receiver"], "c *Cache")

    def test_rust_skeleton_elision(self):
        code = """pub struct Buffer {
    pub capacity: usize,
}

pub enum Protocol {
    TCP,
    UDP,
}

pub trait Transport {
    fn send(&self, data: &[u8]) -> bool;
}

impl Buffer {
    pub fn allocate(size: usize) -> Self {
        let buf = vec![0; size];
        Buffer { capacity: size }
    }
}

pub fn start_service(port: u16) -> Result<(), String> {
    println!("Listening on port {}", port);
    Ok(())
}
"""
        skel = agy_ast.rust_skeleton(code)
        self.assertIn("pub struct Buffer {", skel)
        self.assertIn("pub enum Protocol {", skel)
        self.assertIn("pub trait Transport {", skel)
        self.assertIn("impl Buffer {", skel)
        self.assertIn("pub fn allocate(size: usize) -> Self {", skel)
        self.assertIn("pub fn start_service(port: u16) -> Result<(), String> {", skel)
        # Function bodies must be elided
        self.assertNotIn("vec![0; size]", skel)
        self.assertNotIn("Listening on port", skel)
        self.assertIn("...", skel)

    def test_rust_symbols_extraction(self):
        code = """pub struct Config {
    pub debug: bool,
}

pub enum State {
    Running,
    Stopped,
}

pub trait Runner {
    fn run(&self);
}

impl Runner for Config {
    pub fn execute(&self) -> bool {
        true
    }
}

pub fn init() {
    // init
}
"""
        symbols = agy_ast.rust_symbols(code)
        names = [s["name"] for s in symbols]
        kinds = [s["kind"] for s in symbols]

        self.assertIn("Config", names)
        self.assertIn("State", names)
        self.assertIn("Runner", names)
        self.assertIn("execute", names)
        self.assertIn("init", names)

        self.assertIn("struct", kinds)
        self.assertIn("enum", kinds)
        self.assertIn("trait", kinds)
        self.assertIn("impl", kinds)
        self.assertIn("function", kinds)

    def test_file_dispatcher_routing(self):
        go_file = self.root / "test.go"
        go_file.write_text("package main\nfunc Hello() { println(\"hi\") }", encoding="utf-8")

        rs_file = self.root / "test.rs"
        rs_file.write_text("pub fn greet() { println!(\"hi\"); }", encoding="utf-8")

        go_skel = agy_ast.generate_skeleton(go_file)
        self.assertIn("func Hello() {", go_skel)
        self.assertNotIn("hi", go_skel)

        rs_skel = agy_ast.generate_skeleton(rs_file)
        self.assertIn("pub fn greet() {", rs_skel)
        self.assertNotIn("hi", rs_skel)

        go_syms = agy_ast.extract_symbols(go_file)
        self.assertEqual(go_syms[0]["name"], "Hello")

        rs_syms = agy_ast.extract_symbols(rs_file)
        self.assertEqual(rs_syms[0]["name"], "greet")

    def test_canonical_noise_sanitizer_module(self):
        raw_ansi = "\x1b[32mSUCCESS\x1b[0m: Test passed in \x1b[1m0.45s\x1b[0m"
        clean = noise_sanitizer.strip_ansi(raw_ansi)
        self.assertEqual(clean, "SUCCESS: Test passed in 0.45s")

        short_clean = noise_sanitizer.sanitize_output("On branch main\nnothing to commit, working tree clean", "git status")
        self.assertEqual(short_clean, "ok (working tree clean)")

        cmd_decision = noise_sanitizer.process_command("cargo test", "")
        self.assertEqual(cmd_decision["decision"], "allow")
        self.assertIn("overwrite", cmd_decision)
        self.assertIn("test_output.log", cmd_decision["overwrite"]["CommandLine"])

    def test_cli_sanitize_dispatch(self):
        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.stdout = io.StringIO()
            res = cli.main(["cli.py", "sanitize", "--filter", "clean output"])
            self.assertEqual(res, 0)
            self.assertIn("clean output", sys.stdout.getvalue())

            sys.stdout = io.StringIO()
            res2 = cli.main(["cli.py", "sanitize", "--cmd", "pytest tests/"])
            self.assertEqual(res2, 0)
            self.assertIn("overwrite", sys.stdout.getvalue())
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
