package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"log"
	"os"
	"strings"
)

// FieldDef reprezentuje pojedyncze pole w strukturze
type FieldDef struct {
	Name string `json:"name"`
	Type string `json:"type"`
	Tag  string `json:"tag,omitempty"`
}

// StructDef reprezentuje definicję struktury
type StructDef struct {
	Name   string     `json:"struct_name"`
	Fields []FieldDef `json:"fields"`
}

func main() {
	// Obsługa argumentów linii poleceń
	filePath := flag.String("file", "", "Ścieżka do pliku .go do przeanalizowania")
	flag.Parse()

	if *filePath == "" {
		log.Fatal("Musisz podać ścieżkę do pliku używając flagi -file")
	}

	// Wczytanie treści pliku (potrzebne do wyciągnięcia dokładnego tekstu typów)
	src, err := os.ReadFile(*filePath)
	if err != nil {
		log.Fatalf("Błąd odczytu pliku: %v", err)
	}

	// Tworzenie FileSet do zarządzania pozycjami w pliku
	fset := token.NewFileSet()

	// Parsowanie pliku
	node, err := parser.ParseFile(fset, *filePath, src, parser.ParseComments)
	if err != nil {
		log.Fatalf("Błąd parsowania kodu Go: %v", err)
	}

	var structs []StructDef

	// Przechodzenie przez drzewo składniowe (AST)
	ast.Inspect(node, func(n ast.Node) bool {
		// Szukamy deklaracji typów (type X ...)
		t, ok := n.(*ast.TypeSpec)
		if !ok {
			return true
		}

		// Sprawdzamy, czy dany typ jest strukturą (struct)
		s, ok := t.Type.(*ast.StructType)
		if !ok {
			return true
		}

		structDef := StructDef{
			Name: t.Name.Name,
		}

		// Iterujemy po polach struktury
		for _, field := range s.Fields.List {
			var fieldName string
			
			// Jeśli pole ma nazwę (nie jest osadzone/anonimowe)
			if len(field.Names) > 0 {
				fieldName = field.Names[0].Name
			} else {
				// Obsługa pól anonimowych (embedded struct), np. User w struct Order
				// Pobieramy nazwę typu jako nazwę pola
				fieldName = getTypeString(field.Type, fset, src)
				// Usuwamy ewentualny pakiet (np. models.User -> User)
				if idx := strings.LastIndex(fieldName, "."); idx != -1 {
					fieldName = fieldName[idx+1:]
				}
			}

			// Pobieranie typu jako string prosto z kodu źródłowego
			typeStr := getTypeString(field.Type, fset, src)

			// Pobieranie tagu (usuwamy backticki `)
			tagVal := ""
			if field.Tag != nil {
				tagVal = strings.Trim(field.Tag.Value, "`")
			}

			structDef.Fields = append(structDef.Fields, FieldDef{
				Name: fieldName,
				Type: typeStr,
				Tag:  tagVal,
			})
		}

		structs = append(structs, structDef)
		return false // Nie wchodzimy głębiej w definicję struktury
	})

	// Konwersja do JSON
	jsonData, err := json.MarshalIndent(structs, "", "  ")
	if err != nil {
		log.Fatalf("Błąd generowania JSON: %v", err)
	}

	fmt.Println(string(jsonData))
}

// getTypeString wyciąga fragment kodu źródłowego odpowiadający danemu węzłowi AST.
// Pozwala to uzyskać dokładny typ np. "[]string", "*User", "map[string]int".
func getTypeString(expr ast.Expr, fset *token.FileSet, src []byte) string {
	start := fset.Position(expr.Pos()).Offset
	end := fset.Position(expr.End()).Offset
	return string(src[start:end])
}
